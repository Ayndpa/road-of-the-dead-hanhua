"""Persistent whisper.cpp HTTP server runner.

The old flows spawned ``whisper-cli`` once per clip (or per batch), reloading
the 3 GB model every time, which dominated the runtime for short dialogue
clips.  This module starts one ``whisper-server`` process, keeps the model
resident on the GPU, and feeds it inference requests -- optionally from several
worker threads (``processors``) -- so the GPU stays busy until the run ends.

Usage::

    with WhisperServer(threads=8) as srv:          # processors must stay 1
        results = srv.transcribe_many(
            [(wav_path, prompt, key), ...], concurrency=4
        )

Note: the Vulkan server crashes with ``-p``/processors > 1, so the server keeps
a single context and concurrency is client-side (requests queue on the server).

``asr_vulkan.py``, ``asr.py`` and ``asr_segments.py`` all build on this.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[2]

DEFAULT_SERVER = ROOT / "tools" / "whisper.cpp" / "build" / "bin" / "whisper-server.exe"
DEFAULT_MODEL = ROOT / "tools" / "whisper.cpp" / "models" / "ggml-large-v3.bin"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_port(host: str, port: int, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def _multipart(fields: dict[str, str], files: dict[str, tuple[str, bytes]]) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    body = bytearray()
    for name, value in fields.items():
        body += f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8")
        body += f"{value}\r\n".encode("utf-8")
    for name, (filename, data) in files.items():
        body += f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode("utf-8")
        body += b"Content-Type: application/octet-stream\r\n\r\n"
        body += data
        body += b"\r\n"
    body += f"--{boundary}--\r\n".encode("ascii")
    return bytes(body), f"multipart/form-data; boundary={boundary}"


class WhisperServer:
    """Owns one ``whisper-server`` process and exposes a small JSON client."""

    def __init__(
        self,
        server: str | os.PathLike | None = None,
        model: str | os.PathLike | None = None,
        *,
        host: str = "127.0.0.1",
        port: int | None = None,
        language: str = "en",
        threads: int = 0,
        processors: int = 1,
        suppress_nst: bool = True,
        device: int = -1,
        extra_args: tuple[str, ...] = (),
        startup_timeout: float = 300.0,
        log_file: str | os.PathLike | None = None,
    ) -> None:
        self.server = Path(server or os.environ.get("WHISPER_SERVER", DEFAULT_SERVER))
        self.model = Path(model or os.environ.get("WHISPER_MODEL", DEFAULT_MODEL))
        self.host = host
        self.port = int(port) if port else free_port()
        self.language = language
        self.threads = threads
        self.processors = max(1, processors)
        self.suppress_nst = suppress_nst
        self.device = device
        self.extra_args = tuple(extra_args)
        self.startup_timeout = startup_timeout
        self.log_file = Path(log_file) if log_file else None
        self._proc: subprocess.Popen | None = None
        self._log_handle = None

    # -- lifecycle ---------------------------------------------------------
    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/inference"

    def start(self) -> "WhisperServer":
        if self._proc is not None:
            return self
        if not self.server.exists():
            raise SystemExit(
                f"whisper-server not found: {self.server}\n"
                "run pipeline/tools/fetch-whisper.ps1 first"
            )
        if not self.model.exists():
            raise SystemExit(
                f"model not found: {self.model}\n"
                "run pipeline/tools/fetch-whisper.ps1 first"
            )
        cmd = [
            str(self.server),
            "-m",
            str(self.model),
            "--host",
            self.host,
            "--port",
            str(self.port),
            "-l",
            self.language,
            "-mc",
            "0",
            "-nf",
            "-et",
            "2.4",
        ]
        if self.threads:
            cmd += ["-t", str(self.threads)]
        if self.processors > 1:
            cmd += ["-p", str(self.processors)]
        if self.suppress_nst:
            cmd.append("-sns")
        cmd += list(self.extra_args)

        env = os.environ.copy()
        if self.device >= 0:
            env["GGML_VK_VISIBLE_DEVICES"] = str(self.device)
        if self.log_file:
            self._log_handle = open(self.log_file, "wb")
            out = self._log_handle
        else:
            out = subprocess.DEVNULL
        self._proc = subprocess.Popen(
            cmd, stdout=out, stderr=out, env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if not _wait_port(self.host, self.port, self.startup_timeout):
            self.stop()
            raise SystemExit(f"whisper-server did not come up on port {self.port}")
        return self

    def stop(self) -> None:
        if self._proc is not None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=10)
            except Exception:  # noqa: BLE001
                try:
                    self._proc.kill()
                except Exception:  # noqa: BLE001
                    pass
            self._proc = None
        if self._log_handle is not None:
            try:
                self._log_handle.close()
            except Exception:  # noqa: BLE001
                pass
            self._log_handle = None

    def __enter__(self) -> "WhisperServer":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()

    # -- inference ---------------------------------------------------------
    def transcribe(
        self,
        wav: str | os.PathLike,
        *,
        prompt: str | None = None,
        language: str | None = None,
        response_format: str = "verbose_json",
        no_context: bool = True,
        temperature: float = 0.0,
        retries: int = 3,
        timeout: float = 600.0,
    ) -> dict:
        """POST one WAV to the server and return the decoded JSON response."""
        wav = Path(wav)
        fields: dict[str, str] = {
            "language": language or self.language,
            "response_format": response_format,
            "no_context": "true" if no_context else "false",
            "temperature": str(temperature),
        }
        if prompt:
            fields["prompt"] = prompt
        body, content_type = _multipart(fields, {"file": (wav.name, wav.read_bytes())})
        last: Exception | None = None
        for attempt in range(retries):
            req = urlrequest.Request(
                self.url, data=body, headers={"Content-Type": content_type}
            )
            try:
                with urlrequest.urlopen(req, timeout=timeout) as resp:
                    payload = json.loads(resp.read().decode("utf-8", "replace"))
                if response_format == "text":
                    return {"text": payload if isinstance(payload, str) else payload}
                return payload
            except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                last = exc
                if self._proc is not None and self._proc.poll() is not None:
                    raise RuntimeError(
                        f"whisper-server exited ({self._proc.returncode})"
                    ) from exc
                time.sleep(0.5 * (attempt + 1))
        raise RuntimeError(f"inference failed for {wav.name}: {last}")

    def transcribe_many(
        self,
        jobs: list[tuple],
        *,
        concurrency: int = 4,
        language: str | None = None,
        **opts,
    ) -> list[tuple]:
        """Run ``jobs`` concurrently.

        Each job is ``(wav_path, prompt)`` or ``(wav_path, prompt, key)``.
        Returns ``[(key, response_dict), ...]`` in completion order; ``key``
        defaults to the WAV path.
        """
        norm: list[tuple] = []
        for job in jobs:
            if len(job) == 2:
                norm.append((job[0], job[1], job[0]))
            else:
                norm.append((job[0], job[1], job[2]))
        results: list[tuple] = []
        with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
            futures = {
                pool.submit(
                    self.transcribe, wav, prompt=prompt, language=language, **opts
                ): key
                for wav, prompt, key in norm
            }
            for fut in as_completed(futures):
                key = futures[fut]
                try:
                    results.append((key, fut.result()))
                except Exception as exc:  # noqa: BLE001
                    if "whisper-server exited" in str(exc):
                        raise
                    results.append((key, exc))
        return results


def parse_segments(data: dict) -> list[dict]:
    """Normalise either whisper-server or whisper-cli JSON to our schema."""
    segs: list[dict] = []
    if "segments" in data:  # whisper-server verbose_json (seconds)
        for seg in data.get("segments", []):
            text = str(seg.get("text", "")).strip()
            if not text:
                continue
            segs.append(
                {
                    "start": round(float(seg.get("start", 0.0)), 2),
                    "end": round(float(seg.get("end", 0.0)), 2),
                    "text": text,
                }
            )
        return segs
    for seg in data.get("transcription", []):  # whisper-cli --output-json (ms)
        off = seg.get("offsets", {})
        text = str(seg.get("text", "")).strip()
        if not text:
            continue
        segs.append(
            {
                "start": round(float(off.get("from", 0)) / 1000.0, 2),
                "end": round(float(off.get("to", 0)) / 1000.0, 2),
                "text": text,
            }
        )
    return segs

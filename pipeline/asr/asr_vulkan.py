"""GPU transcription with whisper.cpp's Vulkan backend (AMD on Windows).

Replaces the old ``asr_gpu.py`` (torch-directml + openai-whisper), which was
CPU-bound by DirectML's operator-by-operator fallbacks.

A single ``whisper-server`` process keeps the model resident on the GPU for the
whole run; clips are decoded to 16 kHz mono s16 WAV with PyAV and POSTed to the
server from a small worker pool (``--concurrency``), so the GPU never idles
waiting on a fresh 3 GB model load.  The result schema matches
``pipeline/asr/asr.py`` / the former ``asr_gpu.py`` so caches can be merged.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import tempfile
import time
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from pipeline.asr.whisper_server import (  # noqa: E402
    DEFAULT_MODEL,
    DEFAULT_SERVER,
    WhisperServer,
    parse_segments,
)

SOUNDS = ROOT / "work" / "sounds"
OUT = ROOT / "work" / "asr_gpu.json"

NAME_RE = re.compile(r"^(?P<chid>-?\d+)_(?P<cls>.+)\.mp3$")


def build_manifest(sounds: Path) -> list[dict]:
    items = []
    for p in sorted(sounds.glob("*.mp3")):
        m = NAME_RE.match(p.name)
        if m:
            chid, cls = int(m.group("chid")), m.group("cls")
        else:
            chid, cls = int(p.stem), p.stem
        items.append({"file": p.name, "path": str(p), "chid": chid, "cls": cls})
    return items


def decode16k(path: str, sr: int = 16000) -> np.ndarray:
    import av

    resampler = av.audio.resampler.AudioResampler(format="s16", layout="mono", rate=sr)
    buf = io.BytesIO()
    with av.open(path, mode="r") as container:
        for frame in container.decode(audio=0):
            try:
                outs = resampler.resample(frame)
            except Exception:  # noqa: BLE001
                outs = [frame]
            for f in outs:
                if f is not None:
                    buf.write(f.to_ndarray().tobytes())
    raw = np.frombuffer(buf.getvalue(), dtype=np.int16)
    return raw.astype(np.float32) / 32768.0


def write_wav(path: Path, audio: np.ndarray, sr: int = 16000) -> None:
    pcm = np.clip(audio, -1.0, 1.0)
    pcm = (pcm * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(sr)
        fh.writeframes(pcm.tobytes())


def resolve_server(args) -> Path:
    if args.server:
        return Path(args.server)
    if args.whisper:
        # Backwards compatibility: derive whisper-server next to the given CLI.
        return Path(args.whisper).with_name("whisper-server.exe")
    return DEFAULT_SERVER


def main() -> int:
    # Transcribed text can contain any codepoint (music notes, CJK, ...); the
    # Windows console is often GBK, so never let a print abort the run.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default=os.environ.get("WHISPER_SERVER", ""),
                    help=f"whisper-server binary (default: {DEFAULT_SERVER})")
    ap.add_argument("--whisper", default=os.environ.get("WHISPER_CLI", ""),
                    help="deprecated whisper-cli path; its folder is used to find whisper-server")
    ap.add_argument("--model", default=os.environ.get("WHISPER_MODEL", str(DEFAULT_MODEL)))
    ap.add_argument("--sounds", default=str(SOUNDS))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--language", default="en")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", nargs="*", default=[])
    ap.add_argument("--voice-only", action="store_true")
    ap.add_argument("--filter", default="")
    ap.add_argument("--beam", type=int, default=5)
    ap.add_argument("--threads", type=int, default=0)
    ap.add_argument("--device", type=int, default=-1, help="Vulkan device index (-1 = default)")
    ap.add_argument("--concurrency", type=int, default=4,
                    help="client inference requests in flight (the server queues them)")
    ap.add_argument("--processors", type=int, default=1,
                    help="server processor count; >1 crashes this Vulkan build, so leave at 1")
    ap.add_argument("--batch", type=int, default=0,
                    help="deprecated; kept for compatibility (0 = default)")
    ap.add_argument("--port", type=int, default=0, help="whisper-server port (0 = auto)")
    ap.add_argument("--server-log", default="", help="write server log to this file")
    ap.add_argument(
        "--no-suppress-nst",
        action="store_true",
        help="do not pass -sns (keep non-speech tokens such as music notes)",
    )
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--shards", type=int, default=1)
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--seed", default="", help="json of already-done results")
    ap.add_argument("--dump", nargs="*", default=None, help="print raw ASR text only")
    args = ap.parse_args()

    server_bin = resolve_server(args)
    model = Path(args.model)

    out_path = Path(args.out)
    items = build_manifest(Path(args.sounds))
    if args.filter:
        rx = re.compile(args.filter)
        items = [i for i in items if rx.search(i["cls"])]
    if args.voice_only:
        from pipeline.asr.pick_voice import NOISE_RE, VOICE_RE

        items = [
            i for i in items if VOICE_RE.match(i["cls"]) and not NOISE_RE.match(i["cls"])
        ]
    if args.only:
        wanted = set(args.only)
        items = [i for i in items if i["cls"] in wanted or i["file"] in wanted]

    res: dict = {}
    if out_path.exists() and not args.reset:
        res = json.loads(out_path.read_text(encoding="utf-8"))
    if args.seed and Path(args.seed).exists():
        seed = json.loads(Path(args.seed).read_text(encoding="utf-8"))
        for k, v in seed.items():
            res.setdefault(k, v)
    todo = [i for i in items if i["file"] not in res]
    if args.limit:
        todo = todo[: args.limit]
    if args.shards > 1:
        todo = [x for j, x in enumerate(todo) if j % args.shards == args.shard]
    print(
        f"items={len(items)} cached={len(res)} todo={len(todo)} "
        f"shard={args.shard}/{args.shards} concurrency={args.concurrency}",
        flush=True,
    )
    if not todo:
        return 0

    t0 = time.time()
    extra = ["-bs", str(args.beam)] if args.beam > 0 else []
    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        prepared: list[tuple[dict, Path, float]] = []
        for i, item in enumerate(todo):
            try:
                audio = decode16k(item["path"])
                wav = tmpdir / f"a{i}.wav"
                write_wav(wav, audio)
            except Exception as exc:  # noqa: BLE001
                print(f"  !! {item['cls']}: {type(exc).__name__}: {exc}", flush=True)
                continue
            prepared.append((item, wav, len(audio) / 16000.0))
        if not prepared:
            return 0

        with WhisperServer(
            server=server_bin,
            model=model,
            language=args.language,
            threads=args.threads,
            processors=args.processors,
            suppress_nst=not args.no_suppress_nst,
            device=args.device,
            port=args.port or None,
            extra_args=tuple(extra),
            log_file=(args.server_log or None),
        ) as srv:
            t1 = time.time()
            outcomes = srv.transcribe_many(
                [(wav, None, item["file"]) for item, wav, _ in prepared],
                concurrency=args.concurrency,
                language=args.language,
            )
            per_item = round((time.time() - t1) / len(prepared), 2)

        by_file = {item["file"]: (item, wav, dur) for item, wav, dur in prepared}
        n = 0
        for key, data in outcomes:
            item, _wav, duration = by_file[key]
            n += 1
            if isinstance(data, Exception):
                print(f"  !! {item['cls']}: {type(data).__name__}: {data}", flush=True)
                continue
            try:
                segs = parse_segments(data)
            except Exception as exc:  # noqa: BLE001
                print(f"  !! {item['cls']}: {type(exc).__name__}: {exc}", flush=True)
                continue
            text = " ".join(s["text"] for s in segs).strip()
            res[item["file"]] = {
                "cls": item["cls"],
                "text": text,
                "segments": segs,
                "duration": round(duration, 2),
                "elapsed": per_item,
            }
            out_path.write_text(
                json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8"
            )
            print(
                f"[{n}/{len(prepared)}] {item['cls']} ({duration:.1f}s, "
                f"{per_item:.1f}s) -> {text[:90]!r}",
                flush=True,
            )
    out_path.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"done in {time.time() - t0:.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

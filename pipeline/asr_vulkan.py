"""GPU transcription with whisper.cpp's Vulkan backend (AMD on Windows).

Replaces the old ``asr_gpu.py`` (torch-directml + openai-whisper), which was
CPU-bound by DirectML's operator-by-operator fallbacks.  This drives the
``whisper-cli`` binary built with ``GGML_VULKAN=ON`` (see
``pipeline/fetch-whisper.ps1``) and writes the exact same schema as
``pipeline/asr.py`` / the former ``asr_gpu.py`` so results can be merged and the
cache reused.

The CLI is invoked once per clip; audio is decoded to 16 kHz mono s16 WAV with
PyAV first because whisper-cli only reads WAV.  Segment timestamps come from
whisper-cli's ``--output-json`` (``offsets`` are milliseconds).
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SOUNDS = ROOT / "work" / "sounds"
OUT = ROOT / "work" / "asr_gpu.json"

DEFAULT_WHISPER = ROOT / "tools" / "whisper.cpp" / "build" / "bin" / "whisper-cli.exe"
DEFAULT_MODEL = ROOT / "tools" / "whisper.cpp" / "models" / "ggml-large-v3.bin"

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


def run_whisper_batch(whisper: str, model: str, pairs: list[tuple[Path, Path]], args) -> str:
    """Run one whisper-cli invocation over many clips (model loaded once).

    ``pairs`` is a list of (wav, output-prefix); each pair becomes a ``-f`` /
    ``-of`` couple.  Loading the model once per batch instead of once per clip
    is what makes the whole run fast -- the 3GB model reload otherwise dominates
    for short dialogue clips.
    """
    cmd = [whisper, "-m", model, "-l", args.language, "-oj", "-np"]
    if not args.no_suppress_nst:
        cmd.append("-sns")  # suppress non-speech tokens (music notes, [noise], ...)
    if args.threads:
        cmd += ["-t", str(args.threads)]
    if args.beam > 0:
        cmd += ["-bs", str(args.beam)]
    for wav, prefix in pairs:
        cmd += ["-f", str(wav), "-of", str(prefix)]
    # whisper.cpp/ggml selects the Vulkan device through the environment (the
    # CUDA_VISIBLE_DEVICES equivalent); the CLI has no --device flag.
    env = None
    if args.device >= 0:
        env = os.environ.copy()
        env["GGML_VK_VISIBLE_DEVICES"] = str(args.device)
    proc = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env
    )
    if proc.returncode != 0:
        print(
            f"  !! whisper-cli exited {proc.returncode}: "
            f"{(proc.stderr or proc.stdout).strip()[-300:]}",
            flush=True,
        )
    return proc.stdout or ""


def parse_result(data: dict) -> tuple[str, list[dict]]:
    segs = []
    for seg in data.get("transcription", []):
        off = seg.get("offsets", {})
        segs.append(
            {
                "start": round(float(off.get("from", 0)) / 1000.0, 2),
                "end": round(float(off.get("to", 0)) / 1000.0, 2),
                "text": str(seg.get("text", "")).strip(),
            }
        )
    text = " ".join(s["text"] for s in segs).strip()
    return text, segs


def main() -> int:
    # Transcribed text can contain any codepoint (music notes, CJK, ...); the
    # Windows console is often GBK, so never let a print abort the run.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--whisper", default=os.environ.get("WHISPER_CLI", str(DEFAULT_WHISPER)))
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
    ap.add_argument("--batch",
        type=int,
        default=100,
        help="clips per whisper-cli invocation (the model is loaded once per batch)",
    )
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

    whisper, model = Path(args.whisper), Path(args.model)
    if not whisper.exists():
        raise SystemExit(f"whisper-cli not found: {whisper}\nrun pipeline/fetch-whisper.ps1 first")
    if not model.exists():
        raise SystemExit(f"model not found: {model}\nrun pipeline/fetch-whisper.ps1 first")

    out_path = Path(args.out)
    items = build_manifest(Path(args.sounds))
    if args.filter:
        rx = re.compile(args.filter)
        items = [i for i in items if rx.search(i["cls"])]
    if args.voice_only:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from pick_voice import NOISE_RE, VOICE_RE

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
        f"shard={args.shard}/{args.shards}",
        flush=True,
    )
    if not todo:
        return 0

    t0 = time.time()
    batch_size = max(1, args.batch)
    n = 0
    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        for start in range(0, len(todo), batch_size):
            batch = todo[start : start + batch_size]
            prepared: list[tuple[dict, Path, Path, float]] = []
            for i, item in enumerate(batch):
                try:
                    audio = decode16k(item["path"])
                    wav = tmpdir / f"a{start + i}.wav"
                    write_wav(wav, audio)
                except Exception as exc:  # noqa: BLE001
                    n += 1
                    print(f"  !! {item['cls']}: {type(exc).__name__}: {exc}", flush=True)
                    continue
                prepared.append((item, wav, tmpdir / f"a{start + i}", len(audio) / 16000.0))
            if not prepared:
                continue
            t1 = time.time()
            run_whisper_batch(
                str(whisper), str(model), [(w, p) for _, w, p, _ in prepared], args
            )
            per_item = round((time.time() - t1) / len(prepared), 2)
            saved = 0
            for item, _wav, prefix, duration in prepared:
                n += 1
                js = prefix.with_suffix(".json")
                if not js.exists():
                    print(f"  !! {item['cls']}: no json from whisper-cli", flush=True)
                    continue
                try:
                    data = json.loads(js.read_text(encoding="utf-8"))
                    text, segs = parse_result(data)
                except Exception as exc:  # noqa: BLE001
                    print(f"  !! {item['cls']}: {type(exc).__name__}: {exc}", flush=True)
                    continue
                res[item["file"]] = {
                    "cls": item["cls"],
                    "text": text,
                    "segments": segs,
                    "duration": round(duration, 2),
                    "elapsed": per_item,
                }
                saved += 1
                if saved % 20 == 0:
                    out_path.write_text(
                        json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8"
                    )
                print(
                    f"[{n}/{len(todo)}] {item['cls']} ({duration:.1f}s, "
                    f"{per_item:.1f}s) -> {text[:90]!r}",
                    flush=True,
                )
            out_path.write_text(
                json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8"
            )
    out_path.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"done in {time.time() - t0:.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Transcribe exported SWF sounds with faster-whisper.

Resumable: results are appended to work/asr_results.json keyed by file name.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

# PyAV >= 19 removed the ``metadata_errors`` keyword that faster-whisper still
# passes to ``av.open``. Patch it away before faster-whisper is imported.
import av as _av  # noqa: E402

if "metadata_errors" not in (_av.open.__doc__ or ""):
    _av_open_orig = _av.open

    def _av_open_compat(file, mode="r", **kwargs):
        kwargs.pop("metadata_errors", None)
        return _av_open_orig(file, mode=mode, **kwargs)

    _av.open = _av_open_compat

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SOUNDS = ROOT / "work" / "sounds"
OUT = ROOT / "work" / "asr_results.json"

NAME_RE = re.compile(r"^(?P<chid>-?\d+)_(?P<cls>.+)\.mp3$")


def build_manifest() -> list[dict]:
    items = []
    for p in sorted(SOUNDS.glob("*.mp3")):
        m = NAME_RE.match(p.name)
        if m:
            chid = int(m.group("chid"))
            cls = m.group("cls")
        else:
            chid, cls = int(p.stem), p.stem
        items.append(
            {
                "file": p.name,
                "path": str(p),
                "chid": chid,
                "cls": cls,
                "bytes": p.stat().st_size,
            }
        )
    return items


def load_results(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_results(path: Path, res: dict) -> None:
    path.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="large-v3")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--filter", default="", help="regex on class name")
    ap.add_argument("--only", nargs="*", default=[])
    ap.add_argument("--beam", type=int, default=5)
    ap.add_argument("--threads", type=int, default=16)
    ap.add_argument("--no-vad", action="store_true")
    ap.add_argument("--vad-threshold", type=float, default=0.5)
    ap.add_argument("--vad-min-silence", type=int, default=300)
    ap.add_argument("--vad-min-speech", type=int, default=0)
    ap.add_argument("--no-speech-threshold", type=float, default=0.6)
    ap.add_argument("--log-prob-threshold", type=float, default=-1.0)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--reset", action="store_true", help="ignore cached results")
    ap.add_argument("--force", action="store_true", help="redo selected items")
    ap.add_argument("--voice-only", action="store_true", help="only dialogue classes")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    global OUT
    if args.out:
        OUT = Path(args.out)

    from faster_whisper import WhisperModel

    items = build_manifest()
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

    res = load_results(OUT)
    if args.reset:
        res = {}
        if OUT.exists():
            OUT.unlink()
    todo = [i for i in items if args.force or i["file"] not in res]
    if args.limit:
        todo = todo[: args.limit]

    total_mb = sum(i["bytes"] for i in todo) / 1e6
    print(f"items={len(items)} todo={len(todo)} audio~{total_mb:.1f}MB", flush=True)
    if not todo:
        return 0

    t0 = time.time()
    model = WhisperModel(
        args.model, device="cpu", compute_type="int8", cpu_threads=args.threads
    )
    print(f"model loaded in {time.time() - t0:.1f}s", flush=True)

    for n, item in enumerate(todo, 1):
        t1 = time.time()
        try:
            segments, info = model.transcribe(
                item["path"],
                language="en",
                beam_size=args.beam,
                vad_filter=not args.no_vad,
                vad_parameters={
                    "threshold": args.vad_threshold,
                    "min_silence_duration_ms": args.vad_min_silence,
                    "min_speech_duration_ms": args.vad_min_speech,
                    "speech_pad_ms": 200,
                },
                condition_on_previous_text=False,
                word_timestamps=False,
                no_speech_threshold=args.no_speech_threshold,
                log_prob_threshold=args.log_prob_threshold,
                temperature=args.temperature,
            )
            segs = [
                {
                    "start": round(s.start, 2),
                    "end": round(s.end, 2),
                    "text": s.text.strip(),
                }
                for s in segments
            ]
        except Exception as exc:  # noqa: BLE001
            print(f"  !! {item['cls']}: {exc}", flush=True)
            continue
        text = " ".join(s["text"] for s in segs).strip()
        res[item["file"]] = {
            "cls": item["cls"],
            "text": text,
            "segments": segs,
            "duration": round(info.duration, 2),
            "elapsed": round(time.time() - t1, 2),
        }
        if n % 10 == 0 or n == len(todo):
            save_results(OUT, res)
        print(
            f"[{n}/{len(todo)}] {item['cls']} ({info.duration:.1f}s) -> {text[:90]!r}",
            flush=True,
        )
    save_results(OUT, res)
    print(f"done in {time.time() - t0:.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

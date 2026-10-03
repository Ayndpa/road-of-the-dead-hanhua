"""Transcribe exported SWF sounds through a persistent whisper.cpp server.

Formerly this ran faster-whisper on the CPU with an in-process model.  It now
uses the same resident ``whisper-server`` as the other flows (see
``whisper_server.py``): the model loads once for the whole run and clips are
submitted from a small worker pool.  Silero VAD (faster-whisper) is still used
to find speech regions when VAD is enabled.

Resumable: results are appended to work/asr_results.json keyed by file name.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from pipeline.asr.asr_vulkan import build_manifest, decode16k, write_wav  # noqa: E402
from pipeline.asr.whisper_server import (  # noqa: E402
    DEFAULT_MODEL,
    DEFAULT_SERVER,
    WhisperServer,
    parse_segments,
)

SOUNDS = ROOT / "work" / "sounds"
OUT = ROOT / "work" / "asr_results.json"


def save_results(path: Path, res: dict) -> None:
    path.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default=str(DEFAULT_SERVER))
    ap.add_argument("--model", default=str(DEFAULT_MODEL), help="ggml model path")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--filter", default="", help="regex on class name")
    ap.add_argument("--only", nargs="*", default=[])
    ap.add_argument("--beam", type=int, default=5)
    ap.add_argument("--threads", type=int, default=0)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--processors", type=int, default=1)
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--server-log", default="")
    ap.add_argument("--device", type=int, default=-1)
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

    out_path = Path(args.out) if args.out else OUT

    items = build_manifest(SOUNDS)
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
    if args.reset and out_path.exists():
        out_path.unlink()
        res = {}
    todo = [i for i in items if args.force or i["file"] not in res]
    if args.limit:
        todo = todo[: args.limit]
    print(f"items={len(items)} todo={len(todo)} concurrency={args.concurrency}", flush=True)
    if not todo:
        return 0

    vad = None
    if not args.no_vad:
        from faster_whisper.vad import VadOptions

        vad = VadOptions(
            threshold=args.vad_threshold,
            min_silence_duration_ms=args.vad_min_silence,
            min_speech_duration_ms=args.vad_min_speech,
            speech_pad_ms=200,
        )

    t0 = time.time()
    extra = ["-bs", str(args.beam)] if args.beam > 0 else []
    extra += ["-nth", str(args.no_speech_threshold), "-lpt", str(args.log_prob_threshold)]
    per_item: dict[str, float] = {}
    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        jobs: list[tuple] = []
        durations: dict[str, float] = {}
        offsets: dict[tuple, float] = {}  # (file, span) -> seconds
        for i, item in enumerate(todo):
            try:
                audio = decode16k(item["path"])
            except Exception as exc:  # noqa: BLE001
                print(f"  !! {item['cls']}: {type(exc).__name__}: {exc}", flush=True)
                continue
            durations[item["file"]] = len(audio) / 16000.0
            if vad is not None:
                from faster_whisper.vad import get_speech_timestamps

                spans = get_speech_timestamps(audio, vad)
                if not spans:
                    spans = [{"start": 0, "end": len(audio)}]
            else:
                spans = [{"start": 0, "end": len(audio)}]
            for j, sp in enumerate(spans):
                s, e = int(sp["start"]), int(sp["end"])
                if e <= s:
                    continue
                wav = tmpdir / f"c{i}_{j}.wav"
                write_wav(wav, audio[s:e])
                key = (item["file"], j)
                jobs.append((wav, None, key))
                offsets[key] = s / 16000.0

        by_file: dict[str, list] = {}
        per = 0.0
        if jobs:
            with WhisperServer(
                server=args.server,
                model=args.model,
                threads=args.threads,
                processors=args.processors,
                device=args.device,
                port=args.port or None,
                extra_args=tuple(extra),
                log_file=(args.server_log or None),
            ) as srv:
                t1 = time.time()
                outcomes = srv.transcribe_many(
                    jobs, concurrency=args.concurrency, temperature=args.temperature
                )
                per = round((time.time() - t1) / len(jobs), 2)
            for key, data in outcomes:
                if isinstance(data, Exception):
                    continue
                off = offsets[key]
                for seg in parse_segments(data):
                    by_file.setdefault(key[0], []).append(
                        {
                            "start": round(off + seg["start"], 2),
                            "end": round(off + seg["end"], 2),
                            "text": seg["text"],
                        }
                    )

        n = 0
        for item in todo:
            if item["file"] not in durations:
                continue
            segs = sorted(by_file.get(item["file"], []), key=lambda x: x["start"])
            text = " ".join(s["text"] for s in segs).strip()
            res[item["file"]] = {
                "cls": item["cls"],
                "text": text,
                "segments": segs,
                "duration": round(durations[item["file"]], 2),
                "elapsed": per,
            }
            n += 1
            if n % 10 == 0 or n == len(todo):
                save_results(out_path, res)
            print(
                f"[{n}/{len(todo)}] {item['cls']} ({durations[item['file']]:.1f}s) -> {text[:90]!r}",
                flush=True,
            )
    save_results(out_path, res)
    print(f"done in {time.time() - t0:.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

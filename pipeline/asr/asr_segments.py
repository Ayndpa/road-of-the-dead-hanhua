"""VAD-split + per-segment gain-normalised transcription for hard audio.

The streamed timeline audio is speech buried under music / radio processing.
Splitting on speech regions and normalising each region before decoding
noticeably improves accuracy over one pass on the whole track.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# PyAV >= 19 removed the ``metadata_errors`` kwarg faster-whisper still passes.
import av as _av

if "metadata_errors" not in (_av.open.__doc__ or ""):
    _av_open_orig = _av.open

    def _av_open_compat(file, mode="r", **kwargs):
        kwargs.pop("metadata_errors", None)
        return _av_open_orig(file, mode=mode, **kwargs)

    _av.open = _av_open_compat

import numpy as np  # noqa: E402
from faster_whisper import WhisperModel  # noqa: E402
from faster_whisper.audio import decode_audio  # noqa: E402
from faster_whisper.vad import VadOptions, get_speech_timestamps  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("--model", default="large-v3")
    ap.add_argument("--out", default="")
    ap.add_argument("--threshold", type=float, default=0.25)
    ap.add_argument("--min-speech", type=int, default=200, help="ms")
    ap.add_argument("--min-silence", type=int, default=400, help="ms")
    ap.add_argument("--pad", type=float, default=0.25, help="seconds")
    ap.add_argument("--gain", type=float, default=0.95)
    ap.add_argument("--beam", type=int, default=5)
    ap.add_argument("--threads", type=int, default=16)
    args = ap.parse_args()

    audio = decode_audio(args.audio, sampling_rate=16000)
    print(f"audio {len(audio) / 16000:.1f}s", flush=True)

    vad = VadOptions(
        threshold=args.threshold,
        min_speech_duration_ms=args.min_speech,
        min_silence_duration_ms=args.min_silence,
        speech_pad_ms=int(args.pad * 1000),
    )
    spans = get_speech_timestamps(audio, vad)
    print(f"speech regions: {len(spans)}", flush=True)

    model = WhisperModel(
        args.model, device="cpu", compute_type="int8", cpu_threads=args.threads
    )

    results = []
    for i, sp in enumerate(spans):
        s = max(0, sp["start"] - int(args.pad * 16000))
        e = min(len(audio), sp["end"] + int(args.pad * 16000))
        chunk = audio[s:e].copy()
        peak = float(np.max(np.abs(chunk))) if chunk.size else 0.0
        if peak > 1e-6:
            chunk = chunk * (args.gain / peak)
        segs, info = model.transcribe(
            chunk,
            language="en",
            beam_size=args.beam,
            vad_filter=False,
            condition_on_previous_text=False,
            temperature=0.0,
        )
        segs = list(segs)
        text = " ".join(x.text.strip() for x in segs).strip()
        off = s / 16000.0
        sub = [
            {
                "start": round(off + x.start, 2),
                "end": round(off + x.end, 2),
                "text": x.text.strip(),
            }
            for x in segs
        ]
        results.append(
            {
                "start": round(s / 16000.0, 2),
                "end": round(e / 16000.0, 2),
                "text": text,
                "sub": sub,
            }
        )
        for x in sub:
            print(
                f"      {x['start']:7.2f}-{x['end']:7.2f}  {x['text']}",
                flush=True,
            )
        print(
            f"[{i + 1}/{len(spans)}] {s / 16000:7.2f}-{e / 16000:7.2f} ({peak:.3f}) {text}",
            flush=True,
        )

    out = Path(args.out) if args.out else ROOT / "work" / "stream_segments.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

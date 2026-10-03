"""VAD-split + per-segment gain-normalised transcription for hard audio.

The streamed timeline audio is speech buried under music / radio processing.
Splitting on speech regions and normalising each region before decoding
noticeably improves accuracy over one pass on the whole track.

Transcription runs through a single persistent ``whisper-server`` (see
``whisper_server.py``) rather than a per-chunk CPU model: VAD still comes from
faster-whisper's Silero timestamps, but the actual decode is GPU and the model
stays loaded for the whole stream.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import wave
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
from faster_whisper.audio import decode_audio  # noqa: E402
from faster_whisper.vad import VadOptions, get_speech_timestamps  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from pipeline.asr.whisper_server import (  # noqa: E402
    DEFAULT_MODEL,
    DEFAULT_SERVER,
    WhisperServer,
    parse_segments,
)


def write_wav(path: Path, audio: np.ndarray, sr: int = 16000) -> None:
    pcm = np.clip(audio, -1.0, 1.0)
    pcm = (pcm * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(sr)
        fh.writeframes(pcm.tobytes())


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("--server", default=str(DEFAULT_SERVER))
    ap.add_argument("--model", default=str(DEFAULT_MODEL), help="ggml model path")
    ap.add_argument("--out", default="")
    ap.add_argument("--language", default="en")
    ap.add_argument("--threshold", type=float, default=0.25)
    ap.add_argument("--min-speech", type=int, default=200, help="ms")
    ap.add_argument("--min-silence", type=int, default=400, help="ms")
    ap.add_argument("--pad", type=float, default=0.25, help="seconds")
    ap.add_argument("--gain", type=float, default=0.95)
    ap.add_argument("--beam", type=int, default=5)
    ap.add_argument("--threads", type=int, default=0)
    ap.add_argument("--processors", type=int, default=1)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--server-log", default="")
    ap.add_argument("--device", type=int, default=-1)
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
    if not spans:
        out = Path(args.out) if args.out else ROOT / "work" / "stream_segments.json"
        out.write_text("[]", encoding="utf-8")
        print(f"wrote {out}")
        return 0

    extra = ["-bs", str(args.beam)] if args.beam > 0 else []
    results: dict[int, dict] = {}
    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        jobs: list[tuple] = []
        meta: dict[int, tuple[int, int, float]] = {}
        for i, sp in enumerate(spans):
            s = max(0, sp["start"] - int(args.pad * 16000))
            e = min(len(audio), sp["end"] + int(args.pad * 16000))
            chunk = audio[s:e].copy()
            peak = float(np.max(np.abs(chunk))) if chunk.size else 0.0
            if peak > 1e-6:
                chunk = chunk * (args.gain / peak)
            wav = tmpdir / f"seg{i}.wav"
            write_wav(wav, chunk)
            jobs.append((wav, None, i))
            meta[i] = (s, e, peak)

        with WhisperServer(
            server=args.server,
            model=args.model,
            language=args.language,
            threads=args.threads,
            processors=args.processors,
            device=args.device,
            port=args.port or None,
            extra_args=tuple(extra),
            log_file=(args.server_log or None),
        ) as srv:
            outcomes = srv.transcribe_many(
                jobs, concurrency=args.concurrency, language=args.language
            )

        for idx, data in outcomes:
            s, e, peak = meta[idx]
            if isinstance(data, Exception):
                print(f"  !! region {idx}: {type(data).__name__}: {data}", flush=True)
                sub: list[dict] = []
            else:
                off = s / 16000.0
                sub = [
                    {
                        "start": round(off + x["start"], 2),
                        "end": round(off + x["end"], 2),
                        "text": x["text"],
                    }
                    for x in parse_segments(data)
                ]
            text = " ".join(x["text"] for x in sub).strip()
            results[idx] = {
                "start": round(s / 16000.0, 2),
                "end": round(e / 16000.0, 2),
                "text": text,
                "sub": sub,
            }

    out = Path(args.out) if args.out else ROOT / "work" / "stream_segments.json"
    ordered = [results[i] for i in range(len(spans)) if i in results]
    out.write_text(json.dumps(ordered, ensure_ascii=False, indent=1), encoding="utf-8")
    for i, r in enumerate(ordered):
        print(
            f"[{i + 1}/{len(spans)}] {r['start']:7.2f}-{r['end']:7.2f} {r['text']}",
            flush=True,
        )
        for x in r["sub"]:
            print(
                f"      {x['start']:7.2f}-{x['end']:7.2f}  {x['text']}",
                flush=True,
            )
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""GPU (DirectML) transcription with openai-whisper for AMD Radeon on Windows.

Writes the same schema as pipeline/asr.py so results can be merged.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SOUNDS = ROOT / "work" / "sounds"
OUT = ROOT / "work" / "asr_gpu.json"

NAME_RE = re.compile(r"^(?P<chid>-?\d+)_(?P<cls>.+)\.mp3$")


def build_manifest() -> list[dict]:
    items = []
    for p in sorted(SOUNDS.glob("*.mp3")):
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="large-v3")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", nargs="*", default=[])
    ap.add_argument("--voice-only", action="store_true")
    ap.add_argument("--filter", default="")
    ap.add_argument("--beam", type=int, default=5)
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--shards", type=int, default=1)
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--seed", default="", help="json of already-done results")
    ap.add_argument("--fp16", action="store_true", help="run model in float16")
    ap.add_argument("--dump", nargs="*", default=None, help="print raw ASR text only")
    args = ap.parse_args()

    out_path = Path(args.out)
    items = build_manifest()
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

    import torch_directml
    import whisper

    device = torch_directml.device()
    print(f"dml device: {torch_directml.device_name(0)}", flush=True)
    t0 = time.time()
    model = whisper.load_model(args.model, device="cpu")
    # DirectML cannot move sparse buffers (whisper keeps `alignment_heads` sparse),
    # so densify any sparse buffer before transferring the model to the device.
    for mod in model.modules():
        for key, buf in list(mod._buffers.items()):
            if buf is not None and buf.is_sparse:
                mod._buffers[key] = buf.to_dense()
    model.to(device)
    print(f"model loaded in {time.time() - t0:.1f}s", flush=True)

    for n, item in enumerate(todo, 1):
        t1 = time.time()
        try:
            audio = decode16k(item["path"])
            duration = len(audio) / 16000.0
            result = model.transcribe(
                audio,
                language="en",
                task="transcribe",
                beam_size=args.beam,
                fp16=args.fp16,
                condition_on_previous_text=False,
                temperature=0.0,
                verbose=None,
            )
            text = str(result.get("text", "")).strip()
            segs = [
                {
                    "start": round(float(s["start"]), 2),
                    "end": round(float(s["end"]), 2),
                    "text": str(s["text"]).strip(),
                }
                for s in result.get("segments", [])
            ]
        except Exception as exc:  # noqa: BLE001
            print(f"  !! {item['cls']}: {type(exc).__name__}: {exc}", flush=True)
            continue
        res[item["file"]] = {
            "cls": item["cls"],
            "text": text,
            "segments": segs,
            "duration": round(duration, 2),
            "elapsed": round(time.time() - t1, 2),
        }
        if n % 5 == 0 or n == len(todo):
            out_path.write_text(
                json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8"
            )
        print(
            f"[{n}/{len(todo)}] {item['cls']} ({duration:.1f}s, {time.time() - t1:.1f}s) -> {text[:90]!r}",
            flush=True,
        )
    out_path.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"done in {time.time() - t0:.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

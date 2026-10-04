"""Assemble the patched DTSound.as from the original script and translations."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .constants import ORIGINAL, ROOT
from pipeline.asr.asr_filter import is_stage_direction  # noqa: E402
from pipeline.lib.translations import pairs  # noqa: E402

from .as3 import build_chunks, build_stream_chunks
from .subtitles import build_timed_chunks
from .swf import swf_stage_size
from .templates import IMPORT_BLOCK, METHODS, PLAY_ANCHORS, STATIC_VARS


def generate(original, out, durations=None, stream_timing=None, swf=None,
             min_split_secs: float = 7.5, debug: bool = False,
             stream_offset: float = 1.58) -> Path:
    subs = pairs("voice")            # {cls: (english, chinese)}
    # {stream_NN: (english, chinese)}; drop stage directions such as Whisper's
    # "*Dramatic Music*" so an instrumental bed never shows a subtitle.
    all_stream = pairs("stream")
    stream_subs = {k: (en, zh) for k, (en, zh) in all_stream.items()
                   if not is_stage_direction(en)}
    dropped_stream = len(all_stream) - len(stream_subs)
    items = sorted((k, zh, en) for k, (en, zh) in subs.items() if zh)
    chunks = build_chunks(items)
    print(f"voice subtitle entries: {len(items)}; ", end="")

    durations_map: dict[str, float] = {}
    segments: dict[str, list[dict]] = {}
    if durations and Path(durations).exists():
        for v in json.loads(Path(durations).read_text(encoding="utf-8")).values():
            cls = str(v.get("cls"))
            durations_map[cls] = float(v.get("duration") or 0.0)
            segs = v.get("segments")
            if segs:
                segments[cls] = segs
    timed, timed_chunks = build_timed_chunks(
        {k: zh for k, (_en, zh) in subs.items()},
        durations_map,
        {k: en for k, (en, _zh) in subs.items()},
        min_split_secs,
        segments,
    )
    print(f"{len(timed)} timed clips; ", end="")

    stream: list[dict] = []
    if stream_timing and Path(stream_timing).exists():
        timing = json.loads(Path(stream_timing).read_text(encoding="utf-8"))
        for i, seg in enumerate(timing):
            pair = stream_subs.get(f"stream_{i:02d}")
            if pair:
                en, zh = pair
                stream.append({"start": seg["start"], "end": seg["end"],
                               "zh": zh, "en": en})
    stream_chunks = build_stream_chunks(stream) if stream else '""'
    print(f"{len(stream)} stream entries"
          + (f" ({dropped_stream} non-dialogue skipped)" if dropped_stream else ""))

    src = Path(original).read_text(encoding="utf-8")

    # 1. swap import block + class declaration
    head = "   internal class DTSound extends BasicObject\n   {\n"
    head_end = src.index(head) + len(head)
    src = IMPORT_BLOCK + STATIC_VARS + src[head_end:]

    # 2. hook Play()
    for anchor in PLAY_ANCHORS:
        if anchor in src:
            src = src.replace(anchor, anchor + "         SubtitleOnPlay(this);\n", 1)
            break
    else:
        raise SystemExit("Play() anchor not found")

    # 3. append subtitle methods before the trailing braces
    tail = "   }\n}\n"
    idx = src.rindex(tail)
    methods = METHODS.replace("__SUBTITLE_CHUNKS__", chunks)
    methods = methods.replace("__STREAM_CHUNKS__", stream_chunks)
    methods = methods.replace("__TIMED_CHUNKS__", timed_chunks)
    src = src[:idx] + methods + src[idx:]

    design_w, design_h = swf_stage_size(Path(swf)) if swf else (0.0, 0.0)
    src = src.replace("__DESIGN_W__", f"{design_w:.1f}")
    src = src.replace("__DESIGN_H__", f"{design_h:.1f}")
    print(f"design stage size: {design_w:g}x{design_h:g}")

    src = src.replace("__DBG_MODE__", "true" if debug else "false")
    src = src.replace("__STREAM_OFFSET__", f"{stream_offset:.4f}")

    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(src, encoding="utf-8")
    print(f"wrote {out_path} ({len(src)} chars)")
    return out_path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--durations", default=str(ROOT / "data" / "asr_all.json"),
                    help="asr_all.json for clip durations / speech segments")
    ap.add_argument("--stream-timing", default=str(ROOT / "data" / "stream_timing.json"),
                    help="opening streamed-audio segment start/end")
    ap.add_argument("--min-split-secs", type=float, default=7.5)
    ap.add_argument("--out", required=True)
    ap.add_argument("--original", default=str(ORIGINAL))
    ap.add_argument("--swf", default=str(ROOT / "dist" / "Road-Of-The-Dead.swf"),
                    help="original SWF, used to read the native design stage size")
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--stream-offset", type=float, default=1.58,
                    help="seconds between timeline frame 1 and the stream's t=0")
    args = ap.parse_args()
    generate(args.original, args.out, args.durations, args.stream_timing,
             args.swf, args.min_split_secs, args.debug, args.stream_offset)
    return 0

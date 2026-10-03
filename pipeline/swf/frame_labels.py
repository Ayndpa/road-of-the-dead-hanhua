"""Map top-level (main timeline) FrameLabels to their frame numbers.

Reads the FFDec -dumpSWF text output. Top-level tags are indented 4 spaces,
tags inside sprites are indented 6 spaces.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

LINE_RE = re.compile(r"^[0-9a-f]+:(?P<indent>\s+)(?P<idx>\d+)\.\s+(?P<tag>\w+)")
NAME_RE = re.compile(r'name:\s*"([^"]*)"')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", default=str(ROOT / "work" / "swf_tags.txt"))
    ap.add_argument("--fps", type=float, default=30.0)
    args = ap.parse_args()

    frame = 0
    labels: list[tuple[int, str]] = []
    for line in Path(args.dump).read_text(encoding="utf-8", errors="replace").splitlines():
        m = LINE_RE.match(line)
        if not m:
            continue
        if len(m.group("indent")) != 4:
            continue  # not top level
        tag = m.group("tag")
        if tag == "ShowFrame":
            frame += 1
        elif tag == "FrameLabel":
            nm = NAME_RE.search(line)
            if nm:
                labels.append((frame + 1, nm.group(1)))
    print(f"top-level labels: {len(labels)}  (timeline frames so far: {frame})")
    print(f"{'frame':>7} {'time(s)':>9}  label")
    for f, name in labels:
        print(f"{f:>7} {f / args.fps:>9.2f}  {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

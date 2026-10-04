"""Nudge baked ``DefineText`` blocks in the ROTD2 True Hell build.

The True Hell MOD lays its preloader/passport screen out differently from the
base game: the Newgrounds description sits lower (a gap the base game does not
have), and the "True Hell MOD by DELW_(bilibili)" credit shares the game-title
row, runs off the left edge and uses a larger face.

Each ``--nudge <charId>:<dy>[:<dx>[:<height>]]`` shifts every record's ``y``
(and the clip rect) by ``dy`` twips, shifts the tag ``translatex`` by ``dx``
twips, and optionally overrides every record ``height``.  Positive dy moves the
text down, positive dx moves it right.

Usage:
    python pipeline/ui/nudge_rotd2_layout.py --swf <in.swf> --out <out.swf> --nudge 103:-720 --nudge 11180:700:400:500
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pipeline.lib.align_controls import export_formatted  # noqa: E402

FFDEC = ROOT / "tools" / "ffdec" / "ffdec-cli.jar"


def _shift(m: re.Match[str], delta: int) -> str:
    return f"{m.group(1)}{int(m.group(2)) + delta}"


def transform(famt: str, dy: int, dx: int, height: int | None) -> str:
    famt = re.sub(r"(?m)^(y )(-?\d+)$", lambda m: _shift(m, dy), famt)
    famt = re.sub(r"(?m)^(ymin )(-?\d+)$", lambda m: _shift(m, dy), famt)
    famt = re.sub(r"(?m)^(ymax )(-?\d+)$", lambda m: _shift(m, dy), famt)
    if dx:
        famt = re.sub(r"(?m)^(translatex )(-?\d+)$",
                      lambda m: _shift(m, dx), famt)
    if height is not None:
        famt = re.sub(r"(?m)^height \d+$", f"height {height}", famt)
    return famt


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--swf", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--nudge", action="append", default=[],
                    help="<charId>:<dy>[:<dx>[:<height>]] (repeatable)")
    ap.add_argument("--outdir", default=str(ROOT / "work2" / "nudged"))
    args = ap.parse_args()

    nudges: dict[int, tuple[int, int, int | None]] = {}
    for spec in args.nudge:
        parts = spec.split(":")
        cid = int(parts[0])
        dy = int(parts[1]) if len(parts) > 1 else 0
        dx = int(parts[2]) if len(parts) > 2 else 0
        h = int(parts[3]) if len(parts) > 3 else None
        nudges[cid] = (dy, dx, h)
    if not nudges:
        print("nothing to nudge")
        return 0

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    ids = sorted(nudges)
    dumps = export_formatted(args.swf, ids)

    repl = ["-replace", args.swf, args.out]
    n = 0
    for cid in ids:
        famt = dumps.get(cid, "")
        if not famt:
            print(f"  ! tag {cid} not found")
            continue
        dy, dx, h = nudges[cid]
        p = outdir / f"{cid}.txt"
        p.write_text(transform(famt, dy, dx, h), encoding="utf-8")
        repl += [str(cid), str(p)]
        n += 1
    if n == 0:
        return 0
    proc = subprocess.run(["java", "-jar", str(FFDEC), *repl],
                          capture_output=True, text=True, cwd=str(ROOT))
    if proc.returncode != 0:
        print(proc.stdout[-1200:])
        print(proc.stderr[-1200:], file=sys.stderr)
        return 1
    print(f"nudged {n} tags -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Rescale ROTD2 main-menu labels so the Chinese matches the English metrics.

The main-menu button captions are baked ``DefineText`` tags.  Replacing the Latin
face with the (em-filling) CJK face at the *same* ``height`` makes every label
~1.5x taller than the English it replaces, which flattens the menu's size
hierarchy and pushes the longest caption ("LOST GUNS" -> "丢失的枪械") off the
right edge of the stage.

This pass shrinks each label's ``height`` so the rendered Chinese ink height
equals the original English ink height, and shifts its baseline ``y`` so the
Chinese stays vertically centred on the original English ink.  Horizontal
placement is left alone -- ``align_rotd2.py`` right-aligns these ids onto the
original English right edge afterwards (it needs the *rendered* post-scale ink,
which is why the two passes are separate).

Usage:
    python pipeline/fit_menu_rotd2.py --swf <in.swf> --orig <orig.swf> \
        --out <out.swf> --ids 3276,3277,...
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("ROT_TRANSLATIONS", str(ROOT / "data" / "paratranz2"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from align_controls import (  # noqa: E402
    export_formatted, export_svg_ink, export_svg_raw, header_int,
)
from translations import UI_TRANSLATIONS  # noqa: E402

FFDEC = ROOT / "tools" / "ffdec" / "ffdec-cli.jar"

# Every main-menu / challenge-menu caption (idle + hover text tag).
MENU_IDS = {
    3226, 3227, 3229, 3230, 3232, 3233, 3235, 3236, 3238, 3239,
    3241, 3242, 3244,
    3247, 3249, 3251, 3252, 3254, 3255, 3258, 3259, 3261, 3262,
    3264, 3265, 3267, 3268, 3270, 3271, 3273, 3274, 3276, 3277,
}


def _svg_gy(svg: str) -> float | None:
    """Vertical origin of an FFDec ``text:svg`` dump (sum of the first two groups)."""
    gs = re.findall(r'<g transform="matrix\(([^)]*)\)"', svg)[:2]
    vals = [float(g.split(",")[5]) for g in gs if g.count(",") >= 5]
    return sum(vals) if vals else None


def fit_label(famt: str, ofamt: str, o, b, gy, segs) -> str | None:
    if (not famt or not ofamt or "align" in famt or "align" in ofamt
            or o is None or b is None or gy is None or len(segs) != 1):
        return None
    cur_h = header_int(famt, "height")
    cur_y = header_int(famt, "y")
    if cur_h is None or cur_y is None or cur_h <= 0:
        return None
    en_h = o[3] - o[2]
    zh_h = b[3] - b[2]
    if zh_h <= 0 or en_h <= 0:
        return None
    # Only ever shrink: Chinese read at the Latin em is already too tall.
    scale = min(1.0, en_h / zh_h)
    new_h = max(1, int(round(cur_h * scale)))
    # The ink centre moves with the height because the baseline is fixed; the
    # per-height slope of the ink centre about the baseline is measured from the
    # current render, so the compensating ``y`` can be solved in one shot.
    c_old = (b[2] + b[3]) / 2
    c_en = (o[2] + o[3]) / 2
    baseline = cur_y / 20.0
    slope = (c_old - gy - baseline) / cur_h
    c_pred = gy + baseline + new_h * slope
    new_y = int(round(cur_y + (c_en - c_pred) * 20))
    out = re.sub(r"(?m)^height -?\d+", f"height {new_h}", famt)
    out = re.sub(r"(?m)^y -?\d+", f"y {new_y}", out)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--swf", required=True)
    ap.add_argument("--orig", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ids", default="")
    ap.add_argument("--outdir", default=str(ROOT / "work2" / "fit"))
    args = ap.parse_args()

    ids = [int(x) for x in args.ids.split(",") if x.strip()] if args.ids else sorted(MENU_IDS)
    ids = [i for i in ids if i in MENU_IDS and str(i) in UI_TRANSLATIONS
           and len(UI_TRANSLATIONS[str(i)]) == 1]
    if not ids:
        print("nothing to fit")
        return 0

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    cur = export_formatted(args.swf, ids)
    orig = export_formatted(args.orig, ids)
    oink = export_svg_ink(args.orig, ids)
    bink = export_svg_ink(args.swf, ids)
    raw = export_svg_raw(args.swf, ids)

    repl = ["-replace", args.swf, args.out]
    n = 0
    for sid in ids:
        famt = fit_label(cur.get(sid, ""), orig.get(sid, ""),
                         oink.get(sid), bink.get(sid),
                         _svg_gy(raw.get(sid, "")), UI_TRANSLATIONS[str(sid)])
        if famt is None:
            continue
        p = outdir / f"{sid}.txt"
        p.write_text(famt, encoding="utf-8")
        repl += [str(sid), str(p)]
        n += 1
    if n == 0:
        print("nothing to fit")
        return 0
    proc = subprocess.run(["java", "-jar", str(FFDEC), *repl],
                          capture_output=True, text=True, cwd=str(ROOT))
    if proc.returncode != 0:
        print(proc.stdout[-1200:])
        print(proc.stderr[-1200:], file=sys.stderr)
        return 1
    print(f"rescaled {n} menu labels -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

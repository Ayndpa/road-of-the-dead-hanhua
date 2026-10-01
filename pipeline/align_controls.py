"""Re-align translated UI labels that lost their original alignment.

Some UI labels were drawn right-aligned in the original (the controls list: each
action name ends at a common right edge).  FFDec's text import lays the shorter
Chinese out from the tag's *left* origin, so those rows come out ragged.

This module exports each affected text tag in FFDec's "formatted" form, keeps its
original geometry, and rewrites ``translatex`` so the new Chinese ends where the
English did (right-aligned).  Only static ``DefineText`` tags are touched; dynamic
text fields (which carry their own ``align``) are left alone.

Usage:
    python pipeline/align_controls.py --swf <in.swf> --out <out.swf> --orig <orig.swf>
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ui_text import UI_TRANSLATIONS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FFDEC = ROOT / "tools" / "ffdec" / "ffdec-cli.jar"
CJK_FONT = ROOT / "work" / "fonts" / "ui_cjk.ttf"

# UI labels that were right-aligned in the original artwork
TARGET_IDS = [4383, 4384, 4385, 4386, 4387, 4394, 4397, 4398, 4399, 4402]


def export_formatted(orig: str, ids: list[int]) -> dict[int, str]:
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(
            ["java", "-jar", str(FFDEC), "-selectid", ",".join(map(str, ids)),
             "-format", "text:formatted", "-export", "text", td, orig],
            capture_output=True, text=True, cwd=str(ROOT))
        return {int(p.stem): p.read_text(encoding="utf-8") for p in Path(td).glob("*.txt")}


def ink_width_units(font: TTFont, text: str) -> float:
    gs = font.getGlyphSet()
    cmap = font.getBestCmap()
    hmtx = font["hmtx"].metrics
    upm = font["head"].unitsPerEm
    xmin = None
    xmax = None
    penx = 0.0
    for ch in text:
        g = cmap.get(ord(ch))
        if g is None:
            continue
        bp = BoundsPen(gs)
        gs[g].draw(bp)
        if bp.bounds:
            x0, _y0, x1, _y1 = bp.bounds
            if xmin is None:
                xmin = penx + x0
            xmax = penx + x1
        penx += hmtx[g][0] if g in hmtx else upm
    if xmin is None:
        return 0.0
    return xmax - xmin


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--swf", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--orig", required=True)
    ap.add_argument("--ids", default=",".join(map(str, TARGET_IDS)))
    args = ap.parse_args()

    ids = [int(x) for x in args.ids.split(",") if x.strip()]
    texts = export_formatted(args.orig, ids)
    font = TTFont(CJK_FONT)
    upm = font["head"].unitsPerEm
    outdir = ROOT / "work" / "aligned"
    outdir.mkdir(parents=True, exist_ok=True)

    repl = ["-replace", args.swf, args.out]
    for sid in ids:
        famt = texts.get(sid, "")
        segs = UI_TRANSLATIONS.get(str(sid))
        if not famt or not segs:
            continue
        if "align" in famt:            # dynamic text field: alignment handled by tag
            continue
        body = segs[0]
        xmin = int(re.search(r"xmin (-?\d+)", famt).group(1))
        xmax = int(re.search(r"xmax (-?\d+)", famt).group(1))
        tx = int(re.search(r"translatex (-?\d+)", famt).group(1))
        height = int(re.search(r"\nheight (\d+)", famt).group(1))
        ink_tw = ink_width_units(font, body) * height / upm
        # FFDec's layout, calibrated from the source artwork:
        #   rendered_left  ~ tx/20
        #   rendered_right ~ (0.9474*tx + 0.854*ink_tw)/20
        # -> solve so the rendered centre lands on the centre of the original box
        new_tx = int(round(((xmin + xmax) - 0.854 * ink_tw) / 1.9474))
        famt2 = re.sub(r"translatex (-?\d+)", f"translatex {new_tx}", famt)
        famt2 = re.sub(r"\]\s*[^\]]*$", "]" + body, famt2)
        p = outdir / f"{sid}.txt"
        p.write_text(famt2, encoding="utf-8")
        repl += [str(sid), str(p)]
        print(f"  {sid}: {body!r} tx {tx}->{new_tx} (xmax={xmax}, ink={ink_tw:.0f})")

    if len(repl) <= 3:
        print("nothing to align"); return 0
    proc = subprocess.run(["java", "-jar", str(FFDEC), *repl],
                          capture_output=True, text=True, cwd=str(ROOT))
    if proc.returncode != 0:
        print(proc.stdout[-1200:]); print(proc.stderr[-1200:], file=sys.stderr)
        return 1
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

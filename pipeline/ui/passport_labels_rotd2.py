"""Translate the baked vector caption on the ROTD2 Newgrounds passport button.

The "LET'S DO THIS!" button (``PassportPanel.Login`` -> ``DefineButton2`` 110 ->
``DefineShape`` 105) draws its caption as a solid-black vector path on top of a
bitmap gradient.  The font swap cannot touch it, so the button stays English
while the neighbouring "No, thanks." (a real ``DefineText``) is translated.

This pass exports the shape, replaces the black caption path with the Chinese
label laid out on the original caption's ink box (drawn in the same Dirty-Ego
style CJK face as the menu captions) and re-imports the shape.  The bitmap
gradient fill is preserved by FFDec.

Usage:
    python pipeline/ui/passport_labels_rotd2.py --swf <in.swf> --orig <orig.swf> --out <out.swf>
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("ROT_TRANSLATIONS", str(ROOT / "data" / "paratranz2"))
sys.path.insert(0, str(ROOT))
from fontTools.ttLib import TTFont  # noqa: E402
from pipeline.lib.translations import MENU  # noqa: E402
from pipeline.ui.book_labels_rotd2 import _line_path  # noqa: E402

FFDEC = ROOT / "tools" / "ffdec" / "ffdec-cli.jar"
DISPLAY_FONT = ROOT / "work2" / "fonts" / "ui_cjk.ttf"

# Passport Login button shapes -- the base panel's caption plus the intro
# animation's copy (the game cycles between them, so both must be redrawn or the
# caption flickers back to English).
BUTTON_SHAPES = [105, 108]
# The caption is the only solid-black path; the background is a bitmap gradient.
GROW = 1.12
# Fallback if menu.csv has no key (e.g. after a fresh pull from ParaTranz).
DEFAULT_LABEL = "开始吧！"


def _caption_path(txt: str) -> re.Match[str] | None:
    """The caption path -- black on the panel button, white in the intro copy."""
    return re.search(r'<path\b[^>]*fill="(?:#000000|#ffffff)"[^>]*/>', txt, re.S)


def _bbox(d: str) -> tuple[float, float, float, float]:
    nums = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", d)]
    xs, ys = nums[0::2], nums[1::2]
    return min(xs), max(xs), min(ys), max(ys)


def build_shape_svg(svg_path: str, font: TTFont, text: str) -> str | None:
    txt = Path(svg_path).read_text(encoding="utf-8")
    m = _caption_path(txt)
    if m is None:
        return None
    d = re.search(r'd="([^"]*)"', m.group(0)).group(1)
    fill = re.search(r'fill="(#(?:000000|ffffff))"', m.group(0)).group(1)
    left, right, top, bottom = _bbox(d)
    h = bottom - top
    cn_d = _line_path(font, text, left, right - left,
                      top - h * (GROW - 1) / 2, h * GROW)
    if not cn_d:
        return None
    cn = ('<path d="' + cn_d
          + f'" fill="{fill}" fill-rule="evenodd" stroke="none"/>')
    return txt[:m.start()] + cn + txt[m.end():]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--swf", required=True)
    ap.add_argument("--orig", default=str(ROOT / "dist" / "Road-Of-The-Dead2.swf"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--font", default=str(DISPLAY_FONT))
    ap.add_argument("--shape", type=int, action="append", default=None)
    ap.add_argument("--key", default="PassportLogin")
    ap.add_argument("--text", default="")
    ap.add_argument("--svg-dir", default=str(ROOT / "work2" / "passport_labels"))
    args = ap.parse_args()
    shapes = args.shape or BUTTON_SHAPES

    text = args.text or MENU.get(args.key, "") or DEFAULT_LABEL
    if not text:
        print(f"no menu.csv '{args.key}' translation, skipped")
        return 0

    work = Path(args.svg_dir)
    work.mkdir(parents=True, exist_ok=True)
    font = TTFont(args.font)
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(
            ["java", "-jar", str(FFDEC), "-selectid", ",".join(map(str, shapes)),
             "-format", "shape:svg", "-export", "shape", td, args.orig],
            capture_output=True, text=True, cwd=str(ROOT))
        repl = ["-replace", args.swf, args.out]
        n = 0
        for sid in shapes:
            src = Path(td) / f"{sid}.svg"
            if not src.exists():
                print(f"  ! shape {sid} not exported")
                continue
            svg = build_shape_svg(str(src), font, text)
            if svg is None:
                print(f"  ! shape {sid}: no black caption path, skipped")
                continue
            p = work / f"shape_{sid}.svg"
            p.write_text(svg, encoding="utf-8")
            repl += [str(sid), str(p)]
            n += 1
        if n == 0:
            print("nothing to replace")
            return 0
        proc = subprocess.run(["java", "-jar", str(FFDEC), *repl],
                              capture_output=True, text=True, cwd=str(ROOT))
        if proc.returncode != 0:
            print(proc.stdout[-1200:])
            print(proc.stderr[-1200:], file=sys.stderr)
            return 1
    print(f"redrew passport login button ({n} shapes) -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

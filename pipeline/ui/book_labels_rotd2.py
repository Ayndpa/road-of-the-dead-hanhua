"""Translate the baked vector text on the ROTD2 Survival Guide book icon.

The top-right "SURVIVAL GUIDE" book button (``MC_SurvivalGuideButton``) is hand
drawn ``DefineShape`` art -- the caption is not a ``DefineText``, so the font
swap cannot touch it.  The caption is the only solid-black path in each shape
(the cover art uses tans and browns), and the book cover punches letter-shaped
holes for it.

For each state shape this pass:

* recolours that black caption path to the cover tan, exactly filling the
  letter-shaped holes, and
* appends the Chinese caption as a new black path, laid out on the original
  caption's two line boxes and drawn in the same Dirty-Ego style CJK face as the
  menu captions.

The shape is then replaced with FFDec (an SVG viewport maps 1:1 onto the shape
box, so the geometry is preserved).

Usage:
    python pipeline/ui/book_labels_rotd2.py --swf <in.swf> --out <out.swf>
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
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from fontTools.pens.basePen import BasePen  # noqa: E402
from fontTools.ttLib import TTFont  # noqa: E402
from pipeline.lib.translations import MENU  # noqa: E402


class _FlattenPen(BasePen):
    """Flatten glyph curves to polylines (matches menu_labels' vector style)."""

    def __init__(self, glyph_set, steps: int = 8):
        super().__init__(glyph_set)
        self.steps = steps
        self.contours: list[list[tuple[float, float]]] = []
        self._cur: list[tuple[float, float]] = []

    def _moveTo(self, p): self._cur = [p]
    def _lineTo(self, p): self._cur.append(p)

    def _qCurveToOne(self, p1, p2):
        p0 = self._cur[-1]
        for i in range(1, self.steps + 1):
            t = i / self.steps
            self._cur.append(((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
                              (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]))

    def _curveToOne(self, p1, p2, p3):
        p0 = self._cur[-1]
        for i in range(1, self.steps + 1):
            t = i / self.steps; m = 1 - t
            self._cur.append((m ** 3 * p0[0] + 3 * m * m * t * p1[0] + 3 * m * t * t * p2[0] + t ** 3 * p3[0],
                              m ** 3 * p0[1] + 3 * m * m * t * p1[1] + 3 * m * t * t * p2[1] + t ** 3 * p3[1]))

    def _closePath(self):
        if self._cur:
            self.contours.append(self._cur); self._cur = []

    def _endPath(self):
        self._closePath()


def glyph_data(font: TTFont, text: str):
    """Per-character flattened outlines in font units (y up, origin on baseline)."""
    gs = font.getGlyphSet()
    cmap = font.getBestCmap()
    hmtx = font["hmtx"].metrics
    upm = font["head"].unitsPerEm
    items = []
    for ch in text:
        g = cmap.get(ord(ch))
        if g is None:
            continue
        fp = _FlattenPen(gs)
        gs[g].draw(fp)
        adv = hmtx[g][0] if g in hmtx else upm
        items.append((fp.contours, adv))
    if not items:
        raise ValueError(f"no glyphs for {text!r}")
    return items, upm

FFDEC = ROOT / "tools" / "ffdec" / "ffdec-cli.jar"
DISPLAY_FONT = ROOT / "work2" / "fonts" / "ui_cjk.ttf"

# Survival Guide button state shapes (up, over/down/hit).
BOOK_SHAPES = [3375, 3376]
# The original caption's two lines ("SURVIVAL" / "GUIDE").
LINES = 2
# Cover tan behind the caption; the black path is repainted with this.
COVER = "#ad9a5f"
# Glyph height relative to the original caption line box (slight overshoot reads
# better for CJK, whose ink is denser than the Latin caps).
GROW = 1.15
# The Chinese caption is far more compact than the English it replaces, so each
# line is widened to fill the book cover like ROTD1's menu_labels.py: glyphs are
# stretched up to MAX_H_STRETCH and the remainder absorbed as even, capped
# tracking (MAX_GAP_RATIO of the line height), then the run is centred.
MAX_H_STRETCH = 2.5
MAX_GAP_RATIO = 0.6
LABEL_KEY = "SurvivalGuide"


def _black_path(txt: str) -> re.Match[str] | None:
    return re.search(r'<path\b[^>]*fill="#000000"[^>]*/>', txt, re.S)


def _line_boxes(d: str) -> list[tuple[float, float, float, float]]:
    """Per-line (left, right, top, bottom) of the black caption path."""
    subs = re.findall(r"[Mm][^Mm]*", d)
    boxes = []
    for s in subs:
        nums = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", s)]
        xs, ys = nums[0::2], nums[1::2]
        if xs:
            boxes.append((min(xs), max(xs), min(ys), max(ys)))
    if not boxes:
        return []
    centers = sorted((b[2] + b[3]) / 2 for b in boxes)
    mid = (centers[0] + centers[-1]) / 2
    groups = [[b for b in boxes if (b[2] + b[3]) / 2 <= mid],
              [b for b in boxes if (b[2] + b[3]) / 2 > mid]]

    def box(bs):
        return (min(b[0] for b in bs), max(b[1] for b in bs),
                min(b[2] for b in bs), max(b[3] for b in bs))
    return [box(g) for g in groups if g]


def _line_path(font: TTFont, text: str, box_left: float, box_w: float,
               top: float, ink_h: float) -> str:
    """A path filling the caption line box ``box_left..box_left+box_w``.

    The ink fills ``ink_h`` vertically.  Horizontally the run is widened toward
    the box width -- each glyph stretched up to ``MAX_H_STRETCH``, the remainder
    spread as even, capped tracking, and the whole run centred in the box -- so
    the short Chinese caption fills the cover instead of floating in the middle.
    """
    items, _upm = glyph_data(font, text)
    ys = [p[1] for cs, _adv in items for c in cs for p in c]
    if not ys:
        return ""
    s = ink_h / (max(ys) - min(ys))
    baseline = top + max(ys) * s

    glyphs: list[tuple[list[list[tuple[float, float]]], float, float]] = []
    natural: list[float] = []
    for cs, _adv in items:
        if cs:
            gx0 = min(p[0] for c in cs for p in c)
            gx1 = max(p[0] for c in cs for p in c)
        else:
            gx0 = gx1 = 0.0
        glyphs.append((cs, gx0, gx1))
        natural.append((gx1 - gx0) * s)

    n = len(glyphs)
    total = sum(natural)
    extra = 0.0
    if n and total < box_w:
        extra = min((box_w - total) / n, (MAX_H_STRETCH - 1.0) * (total / n))
    total += extra * n
    if n == 1 or total >= box_w:
        gap, cursor = 0.0, (box_w - total) / 2
    else:
        gap = min((box_w - total) / (n - 1), MAX_GAP_RATIO * ink_h)
        cursor = (box_w - (total + gap * (n - 1))) / 2

    parts = []
    for (cs, gx0, gx1), nat in zip(glyphs, natural):
        ink_w = gx1 - gx0
        sx = (nat + extra) / ink_w if ink_w else 0.0
        x0 = box_left + cursor - gx0 * sx
        for c in cs:
            p2 = [(x0 + x * sx, baseline - y * s) for x, y in c]
            if len(p2) < 3:
                continue
            parts.append(f"M{p2[0][0]:.2f} {p2[0][1]:.2f} " + " ".join(
                f"L{p[0]:.2f} {p[1]:.2f}" for p in p2[1:]) + "Z")
        cursor += nat + extra + gap
    return " ".join(parts)


def build_shape_svg(shape_svg: str, font: TTFont, text: str) -> str | None:
    txt = Path(shape_svg).read_text(encoding="utf-8")
    m = _black_path(txt)
    if m is None:
        return None
    d = re.search(r'd="([^"]*)"', m.group(0)).group(1)
    boxes = _line_boxes(d)
    if len(boxes) != LINES:
        return None
    # Split the Chinese caption evenly over the original lines.
    chars = list(text)
    per = max(1, (len(chars) + LINES - 1) // LINES)
    lines = ["".join(chars[i * per:(i + 1) * per]) for i in range(LINES)]
    paths = []
    for line, box in zip(lines, boxes):
        if not line:
            continue
        h = (box[3] - box[2])
        top = box[2] - h * (GROW - 1) / 2
        paths.append(_line_path(font, line, box[0], box[1] - box[0],
                                top, h * GROW))
    filled = m.group(0).replace('fill="#000000"', f'fill="{COVER}"')
    cn = ('<path d="' + " ".join(paths)
          + '" fill="#000000" fill-rule="evenodd" stroke="none"/>')
    return txt[:m.start()] + filled + cn + txt[m.end():]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--swf", required=True)
    ap.add_argument("--orig", default=str(ROOT / "dist" / "Road-Of-The-Dead2.swf"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--font", default=str(DISPLAY_FONT))
    ap.add_argument("--svg-dir", default=str(ROOT / "work2" / "book_labels"))
    args = ap.parse_args()

    text = MENU.get(LABEL_KEY, "")
    if not text:
        print(f"no menu.csv '{LABEL_KEY}' translation, skipped")
        return 0

    work = Path(args.svg_dir)
    work.mkdir(parents=True, exist_ok=True)
    font = TTFont(args.font)
    if 0x751f not in font.getBestCmap() or 0x5357 not in font.getBestCmap():
        print("display font lacks the guide glyphs, skipped")
        return 0

    # Export the original state shapes, rebuild each with the Chinese caption.
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(
            ["java", "-jar", str(FFDEC), "-selectid",
             ",".join(map(str, BOOK_SHAPES)), "-format", "shape:svg",
             "-export", "shape", td, args.orig],
            capture_output=True, text=True, cwd=str(ROOT))
        replaced = 0
        repl = ["-replace", args.swf, args.out]
        for sid in BOOK_SHAPES:
            src = Path(td) / f"{sid}.svg"
            if not src.exists():
                print(f"  ! shape {sid} not exported")
                continue
            svg = build_shape_svg(str(src), font, text)
            if svg is None:
                print(f"  ! shape {sid}: no two-line caption, skipped")
                continue
            p = work / f"shape_{sid}.svg"
            p.write_text(svg, encoding="utf-8")
            repl += [str(sid), str(p)]
            replaced += 1
        if replaced == 0:
            print("nothing to replace")
            return 0
        proc = subprocess.run(["java", "-jar", str(FFDEC), *repl],
                              capture_output=True, text=True, cwd=str(ROOT))
        if proc.returncode != 0:
            print(proc.stdout[-1200:])
            print(proc.stderr[-1200:], file=sys.stderr)
            return 1
    print(f"redrew Survival Guide caption -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

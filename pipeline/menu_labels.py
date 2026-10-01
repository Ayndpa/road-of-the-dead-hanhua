"""Redraw the main-menu vector labels in the Dirty-Ego-styled Chinese font.

The main menu buttons ("THE GREAT ESCAPE", "HIGHWAY TO HELL", ...) are hand-drawn
``DefineShape`` art, not text, so font swaps can't touch them.  The artwork is also
drawn in **perspective** (text looks like it lies on a road receding away: the top
edge is narrower and the glyphs lean).

Rather than fitting a transform to each shape on its own -- which is unstable for
the short labels (OPTIONS / ACHIEVEMENTS / HIGH SCORES) -- we fit the reliable,
long labels once, normalise the result to the label box and reuse that single
perspective for every label.  Chinese glyph outlines are then pushed through the
homography, flattened to polylines and emitted as a vector SVG at exactly the
original shape's bounds (FFDec maps an SVG viewport 1:1 onto the shape box).

Usage:
    python pipeline/menu_labels.py --swf <in.swf> --out <out.swf>
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
from fontTools.pens.basePen import BasePen
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
FFDEC = ROOT / "tools" / "ffdec" / "ffdec-cli.jar"
DEFAULT_FONT = ROOT / "work" / "fonts" / "ui_cjk.ttf"

# shape id -> (chinese text, fill colour, fill opacity)
MENU_LABELS: dict[int, tuple[str, str, float]] = {
    4307: ("亡命大逃亡", "#cb0000", 0.60),   # StoryMode   THE GREAT ESCAPE
    4308: ("亡命大逃亡", "#aa0000", 1.00),
    4303: ("地狱公路", "#ffffff", 0.38),     # StoryHardcore  HIGHWAY TO HELL
    4304: ("地狱公路", "#ffffff", 0.95),
    4295: ("警察国家", "#ffffff", 0.27),     # MilitaryMode   POLICE STATE
    4296: ("警察国家", "#ffffff", 0.67),
    4299: ("死亡倒计时", "#ffffff", 0.35),   # TimeMode       DEAD ON TIME
    4300: ("死亡倒计时", "#ffffff", 0.86),
    4311: ("选项", "#ffffff", 0.25),         # Options
    4312: ("选项", "#ffffff", 0.61),
    4315: ("成就", "#ffffff", 0.25),         # Achievements
    4316: ("成就", "#ffffff", 0.61),
    4319: ("排行榜", "#ffffff", 0.24),       # HighScores
    4320: ("排行榜", "#ffffff", 0.59),
}

# Shared perspective, normalised to the label box (x, y in 0..1 of box width/height).
# Averaged from the reliable long-label fits: top edge narrower than the bottom,
# left/right edges leaning outward -> the "receding on a road" keystone.
SHARED_NORM = [(0.107, 0.0), (0.921, 0.0), (1.036, 1.0), (-0.023, 1.0)]


class FlattenPen(BasePen):
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
            self._cur.append(((1-t)**2*p0[0] + 2*(1-t)*t*p1[0] + t*t*p2[0],
                              (1-t)**2*p0[1] + 2*(1-t)*t*p1[1] + t*t*p2[1]))

    def _curveToOne(self, p1, p2, p3):
        p0 = self._cur[-1]
        for i in range(1, self.steps + 1):
            t = i / self.steps; m = 1 - t
            self._cur.append((m**3*p0[0] + 3*m*m*t*p1[0] + 3*m*t*t*p2[0] + t**3*p3[0],
                              m**3*p0[1] + 3*m*m*t*p1[1] + 3*m*t*t*p2[1] + t**3*p3[1]))

    def _closePath(self):
        if self._cur:
            self.contours.append(self._cur); self._cur = []

    def _endPath(self):
        self._closePath()


def glyph_polylines(font: TTFont, text: str, size_px: float):
    gs = font.getGlyphSet()
    cmap = font.getBestCmap()
    hmtx = font["hmtx"].metrics
    upm = font["head"].unitsPerEm
    s = size_px / upm
    contours: list[list[tuple[float, float]]] = []
    penx = 0.0
    for ch in text:
        g = cmap.get(ord(ch))
        if g is None:
            continue
        fp = FlattenPen(gs)
        gs[g].draw(fp)
        contours += [[(x * s + penx * s, y * s) for x, y in c] for c in fp.contours]
        penx += hmtx[g][0] if g in hmtx else upm
    if not contours:
        return []
    xs = [p[0] for c in contours for p in c]
    cx = (min(xs) + max(xs)) / 2
    return [[(x - cx, y) for x, y in c] for c in contours]


def export_bounds(orig: str, ids: list[int]) -> dict[int, tuple[int, int]]:
    import re
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        subprocess.run(
            ["java", "-jar", str(FFDEC), "-selectid", ",".join(map(str, ids)),
             "-format", "shape:svg", "-export", "shape", td, orig],
            capture_output=True, text=True, cwd=str(ROOT))
        out: dict[int, tuple[int, int]] = {}
        for p in Path(td).glob("*.svg"):
            tag = re.search(r"<svg\b[^>]*>", p.read_text(encoding="utf-8"))
            if not tag:
                continue
            w = re.search(r'width="([\d.]+)', tag.group(0))
            h = re.search(r'height="([\d.]+)', tag.group(0))
            if w and h:
                out[int(p.stem)] = (round(float(w.group(1))), round(float(h.group(1))))
        return out


def make_svg(text: str, color: str, opacity: float, W: int, H: int, font: TTFont) -> str:
    src = np.float32([[0, 0], [W - 1, 0], [W - 1, H - 1], [0, H - 1]])
    corners = np.float32([[nx * W, ny * H] for nx, ny in SHARED_NORM])
    Hm = cv2.getPerspectiveTransform(src, corners)

    def proj(x, y):
        v = Hm @ np.array([x, y, 1.0])
        return (v[0] / v[2], v[1] / v[2])

    parts = []
    for c in glyph_polylines(font, text, 0.88 * H):
        pts = [proj(W / 2 + x, 0.90 * H - y) for x, y in c]   # baseline near the bottom
        if len(pts) < 3:
            continue
        d = f"M{pts[0][0]:.2f} {pts[0][1]:.2f} " + " ".join(
            f"L{p[0]:.2f} {p[1]:.2f}" for p in pts[1:]) + "Z"
        parts.append(d)
    if not parts:
        raise ValueError(f"empty glyphs for {text!r}")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}">\n'
        f'  <path d="{" ".join(parts)}" fill="{color}" '
        f'fill-opacity="{opacity}" fill-rule="evenodd" stroke="none"/>\n</svg>\n'
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--swf", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--orig", required=True)
    ap.add_argument("--font", default=str(DEFAULT_FONT))
    ap.add_argument("--svg-dir", default=str(ROOT / "menu-labels"))
    ap.add_argument("--ids", default="")
    args = ap.parse_args()

    ids = [int(x) for x in args.ids.split(",") if x.strip()] or sorted(MENU_LABELS)
    ids = [i for i in ids if i in MENU_LABELS]
    bounds = export_bounds(args.orig, ids)
    font = TTFont(args.font)
    svg_dir = Path(args.svg_dir)
    svg_dir.mkdir(parents=True, exist_ok=True)

    repl = ["-replace", args.swf, args.out]
    for sid in ids:
        if sid not in bounds:
            print(f"  ! no shape {sid}, skipped")
            continue
        text, color, opacity = MENU_LABELS[sid]
        W, H = bounds[sid]
        svg = make_svg(text, color, opacity, W, H, font)
        p = svg_dir / f"shape_{sid}.svg"
        p.write_text(svg, encoding="utf-8")
        repl += [str(sid), str(p)]
        print(f"  {sid}: {text} {color} @{opacity}  box {W}x{H}")

    proc = subprocess.run(["java", "-jar", str(FFDEC), *repl],
                          capture_output=True, text=True, cwd=str(ROOT))
    if proc.returncode != 0:
        print(proc.stdout[-1500:]); print(proc.stderr[-1500:], file=sys.stderr)
        return 1
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

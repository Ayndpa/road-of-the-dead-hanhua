"""Redraw the main-menu vector labels in the Dirty-Ego-styled Chinese font.

The main menu buttons ("THE GREAT ESCAPE", "HIGHWAY TO HELL", ...) are hand-drawn
``DefineShape`` art, not text, so font swaps can't touch them.  The artwork is also
drawn in **perspective** (text looks like it lies on a road receding away: the top
edge is narrower and the glyphs lean).

Each label sits at a different spot on the road and therefore has its **own**
keystone -- measured per label from the original shape's per-row ink edge with a
robust line fit (``LABEL_NORM``).  A single averaged perspective over-slanted the
lower, short labels, whose left edge is almost vertical in the original.

Chinese glyph outlines are pushed through that homography -- but **per glyph**, so
a wide (stretched) character is stamped with the affine sampled at its own centre
instead of being twisted by the varying shear of the full perspective -- flattened
to polylines and emitted as a vector SVG at exactly the original shape's bounds
(FFDec maps an SVG viewport 1:1 onto the shape box).

Chinese is far more compact than the Latin originals (5 字 replacing 14 letters),
so drawing at the original glyph height leaves a short label filling only a small
slice of the button.  The glyphs are scaled so their ink fills the full label
**height**, then widened horizontally (up to ``MAX_H_STRETCH``) and spread with
even, capped tracking so the run spans the button -- but never flung out to the
box edges one character at a time, which is what made the short labels
(OPTIONS / ACHIEVEMENTS / HIGH SCORES) look broken.

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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from translations import MENU  # noqa: E402

# The Chinese label text itself comes from the ParaTranz export (menu.csv); only
# the visual styling stays here.
#
# shape id -> menu.csv key
MENU_LABEL_KEYS: dict[int, str] = {
    4307: "StoryMode", 4308: "StoryMode",
    4303: "StoryHardcore", 4304: "StoryHardcore",
    4295: "MilitaryMode", 4296: "MilitaryMode",
    4299: "TimeMode", 4300: "TimeMode",
    4311: "Options", 4312: "Options",
    4315: "Achievements", 4316: "Achievements",
    4319: "HighScores", 4320: "HighScores",
}

# shape id -> (fill colour, fill opacity)
#
# Opacities are the original shapes' own fill alphas, read from the exported
# shape PNGs: every idle white label is alpha 102/255 = 0.40 and the idle red
# "THE GREAT ESCAPE" is 153/255 = 0.60; the hover shapes are fully opaque.
# (The previous values were dimmer than the English originals, which made the
# Chinese labels look washed out next to everything else on the menu.)
MENU_LABEL_STYLE: dict[int, tuple[str, float]] = {
    4307: ("#cb0000", 0.60),   # StoryMode   THE GREAT ESCAPE
    4308: ("#aa0000", 1.00),
    4303: ("#ffffff", 0.40),   # StoryHardcore  HIGHWAY TO HELL
    4304: ("#ffffff", 1.00),
    4295: ("#ffffff", 0.40),   # MilitaryMode   POLICE STATE
    4296: ("#ffffff", 1.00),
    4299: ("#ffffff", 0.40),   # TimeMode       DEAD ON TIME
    4300: ("#ffffff", 1.00),
    4311: ("#ffffff", 0.40),   # Options
    4312: ("#ffffff", 1.00),
    4315: ("#ffffff", 0.40),   # Achievements
    4316: ("#ffffff", 1.00),
    4319: ("#ffffff", 0.40),   # HighScores
    4320: ("#ffffff", 1.00),
}

# shape id -> (chinese text, fill colour, fill opacity)
MENU_LABELS: dict[int, tuple[str, str, float]] = {
    sid: (MENU[MENU_LABEL_KEYS[sid]], colour, opacity)
    for sid, (colour, opacity) in MENU_LABEL_STYLE.items()
}

# Perspective per label, normalised to the label box; order TL, TR, BR, BL.
#
# The original labels sit at different places on the road, so each one has its
# own keystone -- it is NOT one shared transform.  Measured from each original
# shape's per-row ink edge with a robust (Theil-Sen) line fit: the left edge of
# the lower labels is almost vertical (OPTIONS 0.00, HIGH SCORES 0.01) while the
# upper ones lean in hard (POLICE STATE 0.15), and the right edge does the
# opposite.  Reusing one averaged keystone (the old `SHARED_NORM`) therefore
# over-slanted the lower labels' left side and read as "歪" next to the English.
# Corners are kept within 0..1 so the SVG viewport (mapped 1:1 onto the original
# shape box by FFDec) never clips a glyph.
LABEL_NORM: dict[int, list[tuple[float, float]]] = {
    4307: [(0.100, 0.0), (0.888, 0.0), (0.974, 1.0), (0.000, 1.0)],  # THE GREAT ESCAPE
    4303: [(0.109, 0.0), (0.868, 0.0), (0.985, 1.0), (0.000, 1.0)],  # HIGHWAY TO HELL
    4295: [(0.145, 0.0), (0.864, 0.0), (0.958, 1.0), (0.000, 1.0)],  # POLICE STATE
    4299: [(0.127, 0.0), (0.851, 0.0), (0.972, 1.0), (0.000, 1.0)],  # DEAD ON TIME
    4311: [(0.000, 0.0), (0.882, 0.0), (0.978, 1.0), (0.000, 1.0)],  # OPTIONS
    4315: [(0.036, 0.0), (0.922, 0.0), (1.000, 1.0), (0.000, 1.0)],  # ACHIEVEMENTS
    4319: [(0.005, 0.0), (0.931, 0.0), (1.000, 1.0), (0.000, 1.0)],  # HIGH SCORES
}

# hover shape id -> idle shape id (same geometry)
HOVER_SHAPES = {4308: 4307, 4304: 4303, 4296: 4295, 4300: 4299,
                4312: 4311, 4316: 4315, 4320: 4319}

# Fallback for any label without its own measurement.
SHARED_NORM = [(0.100, 0.0), (0.910, 0.0), (0.990, 1.0), (0.000, 1.0)]


def label_norm(sid: int) -> list[tuple[float, float]]:
    base = HOVER_SHAPES.get(sid, sid)
    return LABEL_NORM.get(base, SHARED_NORM)

# Widest a glyph may be stretched horizontally, as a multiple of its natural
# (height-matched) width.  Chinese is compact next to the Latin originals, so
# short labels are widened to fill the button instead of being flung to the
# edges; the cap keeps the strokes from looking smeared.
MAX_H_STRETCH = 2.5
# Largest inter-character gap, as a fraction of the label height.
MAX_GAP_RATIO = 0.6


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


def glyph_data(font: TTFont, text: str):
    """Per-character flattened outlines, in font units with y up and the origin
    on the baseline.

    Returns ``(items, upm)`` where each item is ``(contours, advance, xmin, xmax)``.
    """
    gs = font.getGlyphSet()
    cmap = font.getBestCmap()
    hmtx = font["hmtx"].metrics
    upm = font["head"].unitsPerEm
    items: list[tuple[list[list[tuple[float, float]]], float, float, float]] = []
    for ch in text:
        g = cmap.get(ord(ch))
        if g is None:
            continue
        fp = FlattenPen(gs)
        gs[g].draw(fp)
        adv = hmtx[g][0] if g in hmtx else upm
        if not fp.contours:
            items.append(([], adv, 0.0, 0.0))
            continue
        xs = [p[0] for c in fp.contours for p in c]
        items.append((fp.contours, adv, min(xs), max(xs)))
    if not items:
        raise ValueError(f"no glyphs for {text!r}")
    return items, upm


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


def make_svg(text: str, color: str, opacity: float, W: int, H: int, font: TTFont,
             norm: list[tuple[float, float]]) -> str:
    src = np.float32([[0, 0], [W, 0], [W, H], [0, H]])
    corners = np.float32([[nx * W, ny * H] for nx, ny in norm])
    Hm = cv2.getPerspectiveTransform(src, corners)

    def proj(x, y):
        v = Hm @ np.array([x, y, 1.0])
        return (v[0] / v[2], v[1] / v[2])

    def local_affine(cx, cy, eps=0.25):
        """Homography linearised at (cx, cy): the glyph-local affine.

        The full perspective *twists* anything wider than a Latin letter: across
        one stretched Chinese glyph the local shear varies by tens of degrees, so
        the strokes on one side lean much more than on the other and the
        character reads as crooked.  The original hand-drawn letters only ever
        show a constant italic lean, so each glyph is placed by the perspective
        but stamped with the affine sampled at its own centre -- it keeps the
        road-perspective layout without warping the strokes.
        """
        ox, oy = proj(cx, cy)
        px, py = proj(cx + eps, cy)
        qx, qy = proj(cx, cy + eps)
        return (ox, oy,
                (px - ox) / eps, (qx - ox) / eps,   # d x'/dx, d x'/dy
                (py - oy) / eps, (qy - oy) / eps)   # d y'/dx, d y'/dy

    items, _upm = glyph_data(font, text)

    # Vertical: scale the tallest piece of ink to fill the label height.
    ys = [pt[1] for contours, *_ in items for c in contours for pt in c]
    scale = H / (max(ys) - min(ys))          # font units -> px (vertical)
    baseline = max(ys) * scale               # top of the ink lands on the top edge

    # Horizontal: rather than open huge gaps between a couple of square Chinese
    # glyphs, widen the glyphs themselves toward the button width (up to
    # MAX_H_STRETCH), then absorb what's left as evenly spaced tracking (capped),
    # and centre the whole run.  The run therefore spans the original English
    # button instead of collapsing to a few tiny characters at the box edges.
    n = len(items)
    natural = [(xmax - xmin) * scale for _, _adv, xmin, xmax in items]
    total = sum(natural)
    extra = 0.0
    if n and total < W:
        extra = min((W - total) / n, (MAX_H_STRETCH - 1.0) * (total / n))
    total += extra * n
    if n == 1 or total >= W:
        gap, cursor = 0.0, (W - total) / 2
    else:
        gap = min((W - total) / (n - 1), MAX_GAP_RATIO * H)
        cursor = (W - (total + gap * (n - 1))) / 2

    parts = []
    for (contours, _adv, xmin, _xmax), nat in zip(items, natural):
        ink_w = _xmax - xmin
        sx = (nat + extra) / ink_w if ink_w else 0.0
        x0 = cursor - xmin * sx              # put this glyph's ink at `cursor`
        # Glyph outline in flat label space, then stamped with its local affine.
        flat = [[(x0 + x * sx, baseline - y * scale) for x, y in c] for c in contours]
        pts_all = [p for c in flat for p in c]
        if pts_all:
            gx = [p[0] for p in pts_all]
            gy = [p[1] for p in pts_all]
            cx = (min(gx) + max(gx)) / 2.0
            cy = (min(gy) + max(gy)) / 2.0
            ox, oy, j00, j01, j10, j11 = local_affine(cx, cy)
            for c in flat:
                pts = [(ox + j00 * (p[0] - cx) + j01 * (p[1] - cy),
                        oy + j10 * (p[0] - cx) + j11 * (p[1] - cy)) for p in c]
                if len(pts) < 3:
                    continue
                d = f"M{pts[0][0]:.2f} {pts[0][1]:.2f} " + " ".join(
                    f"L{p[0]:.2f} {p[1]:.2f}" for p in pts[1:]) + "Z"
                parts.append(d)
        cursor += nat + extra + gap
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
        svg = make_svg(text, color, opacity, W, H, font, label_norm(sid))
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

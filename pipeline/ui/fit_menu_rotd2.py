"""Rescale ROTD2 main-menu labels so the Chinese matches the English metrics.

The main-menu button captions are baked ``DefineText`` tags.  Replacing the Latin
face with the (em-filling) CJK face at the *same* ``height`` makes every label
~1.5x taller than the English it replaces, which flattens the menu's size
hierarchy and pushes the longest caption ("LOST GUNS" -> "丢失的枪械") off the
right edge of the stage.

This pass shrinks each label's ``height`` so the rendered Chinese ink height
equals the original English ink height, and shifts its baseline ``y`` so the
Chinese stays vertically centred on the original English ink.

Chinese is more compact than the Latin originals (a few 字 replacing a long
English word), so matching the height still leaves a short label filling only a
small slice of the button.  Following ROTD1's ``menu_labels.py``, the run is then
widened horizontally -- the text matrix ``scalexf`` is stretched toward the
original English ink width, capped at ``MAX_H_STRETCH`` so the strokes do not
smear, and the wide English button therefore comes out filled instead of
collapsing to a few tiny characters in the middle.  Horizontal placement is left
alone -- ``align_rotd2.py`` re-centres these ids afterwards (it needs the
*rendered* post-scale ink, which is why the two passes are separate).

Usage:
    python pipeline/ui/fit_menu_rotd2.py --swf <in.swf> --orig <orig.swf> \
        --out <out.swf> --ids 3276,3277,...
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("ROT_TRANSLATIONS", str(ROOT / "data" / "paratranz2"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline.lib.align_controls import (  # noqa: E402
    export_formatted, export_svg_ink, export_svg_raw, header_int,
)
from pipeline.lib.translations import UI_TRANSLATIONS  # noqa: E402

FFDEC = ROOT / "tools" / "ffdec" / "ffdec-cli.jar"

# Every main-menu / challenge-menu caption (idle + hover text tag).
MENU_IDS = {
    3226, 3227, 3229, 3230, 3232, 3233, 3235, 3236, 3238, 3239,
    3241, 3242, 3244,
    3247, 3249, 3251, 3252, 3254, 3255, 3258, 3259, 3261, 3262,
    3264, 3265, 3267, 3268, 3270, 3271, 3273, 3274, 3276, 3277,
    3283, 3285, 3289, 3291, 3295, 3297, 3300, 3304, 3308, 3310,
    3314, 3317, 3325, 3328,
}

# Main-menu carousel copy is intended to run across the full promo strip.  Use
# tracking for these labels so the CJK glyphs keep their natural proportions.
AD_IDS = {
    3283, 3285, 3295, 3297, 3300, 3304, 3308, 3310,
    3314, 3317, 3325, 3328,
}

# The lower-right utility buttons share one fixed label width.  Shorter labels
# receive the missing width as even inter-character space.
CENTER_SPACED_IDS = {3261, 3262, 3264, 3265, 3267, 3268, 3270, 3271}

# These two menu entries are paired in the original layout.  User Campaigns
# should use the Challenge Modes horizontal scale, while each label keeps its
# own vertical height and alignment.
SHARED_WIDTH_SCALE = {3247: 3273, 3249: 3274}

# Widest the run may be stretched horizontally, as a multiple of its natural
# (height-matched) width.  Mirrors ROTD1's menu_labels.MAX_H_STRETCH: short
# captions are widened to fill the English button instead of leaving a couple of
# square glyphs lost in the middle, and the cap keeps the strokes from smearing.
MAX_H_STRETCH = 2.5
# Once the stretch is capped, the remaining slack is spread between the glyphs;
# the largest inter-character gap is this fraction of the line height (ROTD1's
# menu_labels.MAX_GAP_RATIO).  ``letterspacing`` is in twips (1/20 px) and the tag
# matrix scales it with the glyphs, so 1 unit adds 0.05*sx px to each gap.
MAX_GAP_RATIO = 0.6


def _svg_gy(svg: str) -> float | None:
    """Vertical origin of an FFDec ``text:svg`` dump (sum of the first two groups)."""
    gs = re.findall(r'<g transform="matrix\(([^)]*)\)"', svg)[:2]
    vals = [float(g.split(",")[5]) for g in gs if g.count(",") >= 5]
    return sum(vals) if vals else None


def _header_float(header: str, key: str) -> float | None:
    m = re.search(rf"(?m)^{key} (-?\d+(?:\.\d+)?)", header)
    return float(m.group(1)) if m else None


def fit_label(famt: str, ofamt: str, o, b, gy, segs, sid: int,
              shared_sx: float | None = None,
              utility_width: float | None = None) -> str | None:
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
    # Match the English ink height exactly: Chinese read at the Latin em is ~1.5x
    # too tall, so this normally shrinks, but a short label may still grow to fill.
    scale = en_h / zh_h
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
    # Horizontal fill (ROTD1's menu_labels.py): the run after the height change is
    # ``zh_w * (new_h/cur_h)`` wide, because glyph advances scale with the record
    # height.  Stretch it toward the English ink width -- never shrinking, and
    # capped so the strokes stay clean.  A tag may already carry a scale/tracking
    # from an earlier run (this pass is re-runnable), so undo those first: the SVG
    # ink is measured *after* them and would otherwise be divided twice.
    n = len(segs[0].strip())
    prev_sx = _header_float(famt, "scalexf") or 1.0
    prev_ls = header_int(famt, "letterspacing") or 0
    prev_track = (n - 1) * prev_ls * 0.05 * prev_sx if n > 1 else 0.0
    zh_w_natural = max(0.0, (b[1] - b[0]) - prev_track) / prev_sx
    en_w = o[1] - o[0]
    zh_w_scaled = zh_w_natural * (new_h / cur_h)
    if sid in CENTER_SPACED_IDS:
        sx = 1.0
    elif shared_sx is not None:
        sx = shared_sx
    elif en_w > 0 and zh_w_scaled > 0:
        sx = max(1.0, min(MAX_H_STRETCH, en_w / zh_w_scaled))
    else:
        sx = 1.0
    out = re.sub(r"(?m)^height -?\d+", f"height {new_h}", famt)
    out = re.sub(r"(?m)^y -?\d+", f"y {new_y}", out)
    # Tag-level text-matrix scale.  ``scaleyf`` is written even at 1.0 because
    # FFDec reads a missing scaleyf as 0 and would flatten the glyphs.
    out = re.sub(r"(?m)^scalexf .*\n?", "", out)
    out = re.sub(r"(?m)^scaleyf .*\n?", "", out)
    out = re.sub(r"(?m)^letterspacing .*\n?", "", out)
    out = re.sub(r"(?m)^spacing(?:pair)? .*\n?", "", out)
    end = out.index("]")
    out = out[:end] + f"scalexf {sx:.4f}\nscaleyf 1.0000\n" + out[end:]
    # Tracking: when the stretch is capped the run is still short, so spread the
    # remainder evenly between the glyphs (ROTD1's menu_labels.py) -- this fills
    # even a two-character caption without smearing the strokes any further.
    if n > 1 and sid in AD_IDS:
        slack = en_w - sx * zh_w_scaled
        if slack > 0:
            ls = int(round(slack / ((n - 1) * 0.05 * sx)))
            ls = min(ls, int(round(MAX_GAP_RATIO * en_h / (0.05 * sx))))
            rec = out.index("]", end + 1)
            out = out[:rec] + f"letterspacing {ls}\n" + out[rec:]
    elif n > 1 and sid in CENTER_SPACED_IDS and utility_width is not None:
        slack = max(0.0, utility_width - zh_w_scaled)
        ls = int(round(slack / ((n - 1) * 0.05 * sx)))
        rec = out.index("]", end + 1)
        if ls > 0:
            out = out[:rec] + f"letterspacing {ls}\n" + out[rec:]
    elif n > 1 and sx >= MAX_H_STRETCH - 1e-6:
        slack = en_w - sx * zh_w_scaled
        if slack > 0:
            ls = int(round(slack / ((n - 1) * 0.05 * sx)))
            ls = min(ls, int(round(MAX_GAP_RATIO * en_h / (0.05 * sx))))
            rec = out.index("]", end + 1)      # end of the record header
            out = out[:rec] + f"letterspacing {ls}\n" + out[rec:]
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

    # Use the widest translated utility caption as a shared slot width.  This
    # keeps Options / Achievements / Highscores aligned with Credits without
    # stretching the glyphs themselves.
    utility_width: float | None = None
    for sid in sorted(CENTER_SPACED_IDS & set(ids)):
        famt = cur.get(sid, "")
        o = oink.get(sid)
        b = bink.get(sid)
        cur_h = header_int(famt, "height") if famt else None
        if not famt or o is None or b is None or cur_h is None or cur_h <= 0:
            continue
        zh_h = b[3] - b[2]
        en_h = o[3] - o[2]
        if zh_h <= 0 or en_h <= 0:
            continue
        n = len(UI_TRANSLATIONS[str(sid)][0].strip())
        prev_sx = _header_float(famt, "scalexf") or 1.0
        prev_ls = header_int(famt, "letterspacing") or 0
        prev_track = (n - 1) * prev_ls * 0.05 * prev_sx if n > 1 else 0.0
        natural = max(0.0, (b[1] - b[0]) - prev_track) / prev_sx
        width = natural * en_h / zh_h
        utility_width = width if utility_width is None else max(utility_width, width)

    shared_sx: dict[int, float] = {}
    for target, source in SHARED_WIDTH_SCALE.items():
        famt = cur.get(source, "")
        ofamt = orig.get(source, "")
        o = oink.get(source)
        b = bink.get(source)
        if not famt or not ofamt or o is None or b is None:
            continue
        cur_h = header_int(famt, "height")
        prev_sx = _header_float(famt, "scalexf") or 1.0
        prev_ls = header_int(famt, "letterspacing") or 0
        n = len(UI_TRANSLATIONS[str(source)][0].strip())
        prev_track = (n - 1) * prev_ls * 0.05 * prev_sx if n > 1 else 0.0
        zh_w_natural = max(0.0, (b[1] - b[0]) - prev_track) / prev_sx
        en_w = o[1] - o[0]
        if cur_h and zh_w_natural > 0 and en_w > 0:
            zh_w_scaled = zh_w_natural * (o[3] - o[2]) / max(1, b[3] - b[2])
            shared_sx[target] = max(1.0, min(MAX_H_STRETCH, en_w / zh_w_scaled))

    repl = ["-replace", args.swf, args.out]
    n = 0
    for sid in ids:
        famt = fit_label(cur.get(sid, ""), orig.get(sid, ""),
                 oink.get(sid), bink.get(sid),
                         _svg_gy(raw.get(sid, "")), UI_TRANSLATIONS[str(sid)], sid,
                 shared_sx.get(sid), utility_width)
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

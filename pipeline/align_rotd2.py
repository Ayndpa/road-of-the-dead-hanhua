"""Re-align translated ROTD2 UI labels that lost their alignment.

FFDec's text import lays the (often shorter) Chinese out from the original
English text's origin, so labels the original centred come out off-axis.  This
pass mirrors ``align_controls.py``: export each affected static ``DefineText``
tag in FFDec's "formatted" form, measure the rendered ink from an SVG dump
(font-agnostic), and move the text back onto the original ink.

- Single-record tag: rewrite the tag-level ``translatex`` so the Chinese ink sits
  on the original English ink centre.
- Multi-record block: rewrite each record's ``x`` so every line lines up.  The
  original block's own alignment is detected (common centre / left / right edge)
  and preserved, then the tag's clip rect is widened so nothing is cut.

Only static tags are touched; dynamic text fields (``DefineEditText``, which carry
their own ``align``) are left alone.

Usage:
    python pipeline/align_rotd2.py --swf <in.swf> --orig <orig.swf> --out <out.swf> --ids 1,2,3
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
    build_formatted, export_formatted, export_svg_ink, export_svg_raw,
    header_int, parse_formatted, svg_line_boxes, widen_bounds,
)
from translations import UI_TRANSLATIONS  # noqa: E402

FFDEC = ROOT / "tools" / "ffdec" / "ffdec-cli.jar"
PAD = 20
# Single-record labels anchored to the screen's right edge.  The English "Skip"
# sits at the left of a wide box with room to its right, but the stage ends just
# past the English ink, so the wider Chinese overflows unless it keeps the right
# edge (see ROTD1's RIGHT_ALIGN_IDS).  The main-menu captions are centred like
# every other label; the fit pass has already shortened them so their ink no
# longer overflows the English box.
RIGHT_ALIGN_IDS = {
    10186, 10187,
}

# These four utility buttons are centred within their full-width bars, not on
# the original English ink (which is offset inside the bar).
CENTER_ALIGN_IDS = {
    3247, 3249, 3251, 3252, 3261, 3262, 3264, 3265, 3267, 3268,
    3270, 3271, 3273, 3274, 3276, 3277,
}

# The button artwork is left-anchored in the exported button frame while the
# original English captions were right-aligned.  Once the Chinese captions
# share one width, move each pair back onto the artwork's visual centre.
UTILITY_VISUAL_CENTER_SHIFT_PX = {
    3261: -65.0, 3262: -65.0,       # Credits
    3264: -39.0, 3265: -39.0,       # Highscores
    3267: -21.5, 3268: -21.5,       # Achievements
    3270: -63.5, 3271: -63.5,       # Options
}

# The pause menu's Resume/Abort captions sit in the same left-anchored bar
# artwork as the utility buttons, but the bar is drawn in the road's perspective
# so its rendered bounding box reads far right of the bar the player sees; the
# "centred on the artwork" axis used for the utility buttons is therefore wrong
# here.  The original English "Resume" already sits on the bar's visual axis, so
# keep Resume on its English centre and pull Abort left onto that same axis (the
# English pair was right-aligned at a shared edge, which reads off-centre).
PAUSE_BUTTON_VISUAL_CENTER_SHIFT_PX = {
    3173: -10.3, 3174: -10.3,       # Abort -> Resume's axis
    3177: 0.0, 3178: 0.0,           # Resume -> original English centre
}

# The menu bars share a visible right edge at x=3250 twips.  The Lost Guns
# trapezoid extends past that edge, so its visual centre must exclude the right
# overflow instead of using the full stored DefineText bounds.
MENU_RIGHT_TWIPS = 3250

# The four utility captions (Options / Achievements / Highscores / Credits) are
# centred by the normal path; their shared character-sized tracking is added by
# ``fit_menu_rotd2.py`` before this pass measures the rendered ink.


def _ink_record_indices(records: list[tuple[str, str]]) -> list[int]:
    """Indices of the records that actually draw visible glyphs."""
    return [i for i, (_h, text) in enumerate(records) if text.strip()]


def visible_center(dump: str) -> float | None:
    """Return the centre after clipping the menu's right-side overflow."""
    xmin = header_int(dump, "xmin")
    xmax = header_int(dump, "xmax")
    if xmin is None or xmax is None:
        return None
    left = xmin
    right = min(MENU_RIGHT_TWIPS, xmax)
    if right <= left:
        return (xmin + xmax) / 2
    return (left + right) / 2


def align_multi(dump: str, odump: str, osvg: str, bsvg: str) -> str | None:
    """Re-centre every line of a multi-record static tag on the original line.

    FFDec lays each translated record out from the *English* record's ``x``
    origin.  The original author set those per line so every English line is
    centred on one axis; Chinese lines have different widths, so keeping the
    origin leaves them ragged and (when wider) clipped.  Measure the original
    and built ink of each line and shift the matching record's ``x`` onto the
    original centre, then widen the clip rect so nothing is cut.
    """
    if not dump or not odump or not osvg or not bsvg:
        return None
    # Dynamic text fields carry their own ``align``; leave them alone.
    if "align" in dump or "align" in odump:
        return None
    tag, pre, recs = parse_formatted(dump)
    _otag, _opre, orecs = parse_formatted(odump)
    ink = _ink_record_indices(recs)
    oink = _ink_record_indices(orecs)
    olines = svg_line_boxes(osvg)
    blines = svg_line_boxes(bsvg)
    if not (len(ink) == len(oink) == len(olines) == len(blines)):
        return None
    bxmin = header_int(dump, "xmin")
    bxmax = header_int(dump, "xmax")
    if bxmin is None or bxmax is None:
        return None

    # Preserve the original block's alignment: a centred block has a common
    # centre, a list has a common left or right edge.  Pick whichever edge is
    # tightest in the English original (margin avoids calling equal-width centred
    # text left-aligned).
    lefts = [l for l, _r in olines]
    rights = [r for _l, r in olines]
    centres = [(l + r) / 2 for l, r in olines]
    sl = max(lefts) - min(lefts)
    sr = max(rights) - min(rights)
    sc = max(centres) - min(centres)
    if sl <= sr and sl <= sc - 1.0:
        mode = "left"
    elif sr <= sl and sr <= sc - 1.0:
        mode = "right"
    else:
        mode = "center"

    deltas: dict[int, float] = {}
    for k, ridx in enumerate(ink):
        if mode == "left":
            want, have = olines[k][0], blines[k][0]
        elif mode == "right":
            want, have = olines[k][1], blines[k][1]
        else:
            want = (olines[k][0] + olines[k][1]) / 2
            have = (blines[k][0] + blines[k][1]) / 2
        d = (want - have) * 20
        if abs(d) >= 1:
            deltas[ridx] = d
    if not deltas:
        return None

    new_records: list[tuple[str, str]] = []
    minl: float | None = None
    maxr: float | None = None
    for idx, (hdr, text) in enumerate(recs):
        if idx in deltas:
            d = deltas[idx]
            m = re.search(r"(?m)^x (-?\d+)$", hdr)
            old_x = int(m.group(1)) if m else 0
            new_x = int(round(old_x + d))
            hdr = (re.sub(r"(?m)^x -?\d+$", f"x {new_x}", hdr) if m
                   else hdr + ("" if hdr.endswith("\n") else "\n") + f"x {new_x}\n")
            k = ink.index(idx)
            l = bxmin + blines[k][0] * 20 + d
            r = bxmin + blines[k][1] * 20 + d
            minl = l if minl is None else min(minl, l)
            maxr = r if maxr is None else max(maxr, r)
        new_records.append((hdr, text))

    famt = build_formatted(tag, pre, new_records)
    if minl is not None and maxr is not None:
        famt = re.sub(r"(?m)^xmin -?\d+", f"xmin {min(bxmin, int(minl) - PAD)}", famt)
        famt = re.sub(r"(?m)^xmax -?\d+", f"xmax {max(bxmax, int(maxr) + PAD)}", famt)
    return famt


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--swf", required=True, help="localised SWF (already translated)")
    ap.add_argument("--orig", required=True, help="original English SWF")
    ap.add_argument("--out", required=True)
    ap.add_argument("--ids", required=True, help="candidate char ids (comma separated)")
    ap.add_argument("--outdir", default=str(ROOT / "work2" / "aligned"))
    args = ap.parse_args()

    ids = [int(x) for x in args.ids.split(",") if x.strip()]
    ids = [i for i in ids if str(i) in UI_TRANSLATIONS]
    # A tag that is one record gets its whole tag-level ``translatex`` moved; a
    # multi-record block needs each line's record-level ``x`` moved instead.
    single = [i for i in ids if len(UI_TRANSLATIONS[str(i)]) == 1]
    multi = [i for i in ids if len(UI_TRANSLATIONS[str(i)]) > 1]
    if not single and not multi:
        print("nothing to align")
        return 0

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    cur = export_formatted(args.swf, ids)
    ofmt = export_formatted(args.orig, ids)

    repl = ["-replace", args.swf, args.out]
    n = 0

    if single:
        oink = export_svg_ink(args.orig, single)
        bink = export_svg_ink(args.swf, single)
        for sid in single:
            famt = cur.get(sid, "")
            ofamt = ofmt.get(sid, "")
            segs = UI_TRANSLATIONS[str(sid)]
            o, b = oink.get(sid), bink.get(sid)
            if (not famt or not ofamt or "align" in famt or "align" in ofamt
                    or o is None or b is None):
                continue
            bxmin = header_int(famt, "xmin")
            bxmax = header_int(famt, "xmax")
            bymin = header_int(famt, "ymin")
            bymax = header_int(famt, "ymax")
            oxmin = header_int(ofamt, "xmin")
            oxmax = header_int(ofamt, "xmax")
            tx = header_int(famt, "translatex")
            if None in (bxmin, bxmax, bymin, bymax, oxmin, oxmax, tx):
                continue
            if sid in RIGHT_ALIGN_IDS:
                desired = oxmin + o[1] * 20      # original English right edge
                built_edge = bxmin + b[1] * 20
            elif sid in CENTER_ALIGN_IDS:
                # The DefineText bounds include empty space and are not the
                # button's visual axis.  Use the rendered English ink just as
                # the normal centring path does; otherwise short CJK labels
                # drift right toward the shared clipped bound.
                desired = oxmin + (o[0] + o[1]) / 2 * 20
                desired += UTILITY_VISUAL_CENTER_SHIFT_PX.get(sid, 0.0) * 20
                built_edge = bxmin + (b[0] + b[1]) / 2 * 20
            else:
                desired = oxmin + (o[0] + o[1]) / 2 * 20   # English ink centre
                desired += PAUSE_BUTTON_VISUAL_CENTER_SHIFT_PX.get(sid, 0.0) * 20
                built_edge = bxmin + (b[0] + b[1]) / 2 * 20
            new_tx = int(round(tx - (built_edge - desired)))
            if new_tx == tx:
                continue
            s = new_tx - tx
            famt2 = re.sub(r"translatex (-?\d+)", f"translatex {new_tx}", famt)
            famt2 = re.sub(r"\]\s*[^\]]*$", "]" + segs[0], famt2)
            famt2 = widen_bounds(famt2, bxmin, bxmax, bymin, bymax,
                                 bxmin + b[0] * 20 + s, bxmin + b[1] * 20 + s,
                                 bymin + b[2] * 20, bymin + b[3] * 20)
            p = outdir / f"{sid}.txt"
            p.write_text(famt2, encoding="utf-8")
            repl += [str(sid), str(p)]
            n += 1

    if multi:
        oraw = export_svg_raw(args.orig, multi)
        braw = export_svg_raw(args.swf, multi)
        for sid in multi:
            famt2 = align_multi(cur.get(sid, ""), ofmt.get(sid, ""),
                                oraw.get(sid, ""), braw.get(sid, ""))
            if famt2 is None:
                continue
            p = outdir / f"{sid}.txt"
            p.write_text(famt2, encoding="utf-8")
            repl += [str(sid), str(p)]
            n += 1

    if n == 0:
        print("nothing to align")
        return 0
    proc = subprocess.run(["java", "-jar", str(FFDEC), *repl],
                          capture_output=True, text=True, cwd=str(ROOT))
    if proc.returncode != 0:
        print(proc.stdout[-1200:])
        print(proc.stderr[-1200:], file=sys.stderr)
        return 1
    print(f"re-centred {n} labels -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

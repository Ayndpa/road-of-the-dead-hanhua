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
# The labels re-centred by ink metrics are body text (Modern No. 20 -> serif);
# MULTI_TARGET_IDS (the warning title) keeps the decorative Dirty Ego face.
DISPLAY_FONT = ROOT / "work" / "fonts" / "ui_cjk.ttf"
BODY_FONT = ROOT / "work" / "fonts" / "ui_body.ttf"

# Static single-record UI labels that are centred inside their own original box.
# The original English was centred for these, so centring the Chinese keeps the
# look; the box is wide enough that the shorter Chinese never clips.
TARGET_IDS = [
    # options panel (sprite 4430)
    4407, 4414, 4424, 4428, 4429, 4408, 4409, 4411, 4412,
    4415, 4416, 4418, 4419, 4421, 4422, 4425, 4426,
    # warning screen title
    4026,
]
COMMON_CENTRE_GROUPS = [
    [4407, 4414, 4424],  # options centre (same sprite matrix -> common screen axis)
]

# Multi-record static labels.  Each record is one drawn line; FFDec re-imports
# them all at the tag's left origin, so the shorter Chinese rows come out ragged.
# Every record is re-centred on the centre of the original English block.
MULTI_TARGET_IDS = [
    4025,  # warning body: three red lines, centred as a block
]

# Labels anchored to the right edge.  The original English was right-aligned
# (the controls list: every action name ends on one common screen edge) and the
# Chinese is imported at the tag's left origin, so it must be shifted to line the
# right edges back up.  These are right-aligned on the original ink, and their
# stored bounds are widened because Flash clips static text to that rect.
RIGHT_ALIGN_IDS = [
    # controls list (sprite 4404)
    4383,  # 左转
    4384,  # 右转
    4385,  # 加速
    4386,  # 手刹
    4387,  # 喇叭
    4394,  # 画质
    4397,  # 雨刷
    4398,  # 攻击
    4399,  # 刹车
    4402,  # 感知
    # in-game "SKIP" button
    4095,  # idle
    4096,  # over
    # garage upgrade list (sprite 4024): every name ends on one screen edge
    3953,  # 感知      Perception
    3954,  # 挡风玻璃  Windshield
    3955,  # 引擎      Engine
    3956,  # 轮胎      Tires
    3957,  # 防弹衣    Body Armor
    3958,  # 枪械      Firearm
    3959,  # 保险杠    Bumper
    3967,  # 喇叭      Horn
]


def export_formatted(orig: str, ids: list[int]) -> dict[int, str]:
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(
            ["java", "-jar", str(FFDEC), "-selectid", ",".join(map(str, ids)),
             "-format", "text:formatted", "-export", "text", td, orig],
            capture_output=True, text=True, cwd=str(ROOT))
        return {int(p.stem): p.read_text(encoding="utf-8") for p in Path(td).glob("*.txt")}


_NUM = re.compile(r"-?\d+(?:\.\d+)?")


def svg_ink(txt: str) -> tuple[float, float, float, float] | None:
    """Ink box ``(left, right, top, bottom)`` of an FFDec ``text:svg`` dump.

    The dump draws each glyph with a ``<use transform="matrix(sx 0 0 sy ex ey)">``
    referencing a path in font units, wrapped in two translating ``<g>`` groups.
    """
    glyphs: dict[str, tuple[float, float, float, float]] = {}
    for m in re.finditer(r'<g id="([^"]+)">\s*<path d="([^"]+)"', txt):
        nums = [float(v) for v in _NUM.findall(m.group(2))]
        xs, ys = nums[0::2], nums[1::2]
        if xs:
            glyphs[m.group(1)] = (min(xs), max(xs), min(ys), max(ys))
    gs = re.findall(r'<g transform="matrix\(([^)]*)\)"', txt)[:2]
    gx = sum(float(g.split(",")[4]) for g in gs)
    gy = sum(float(g.split(",")[5]) for g in gs)
    box = [None, None, None, None]
    for use in re.findall(r'<use\b[^>]*>', txt):
        m = re.search(r'transform="matrix\(([^)]*)\)"', use)
        href = re.search(r'xlink:href="#([^"]+)"', use)
        if not m or not href:
            continue
        nums = [float(v) for v in m.group(1).split(",")]
        sx, sy, ex, ey = nums[0], nums[3], nums[4], nums[5]
        bounds = glyphs.get(href.group(1))
        if bounds is None:
            continue
        vals = (gx + ex + sx * bounds[0], gx + ex + sx * bounds[1],
                gy + ey + sy * bounds[2], gy + ey + sy * bounds[3])
        for i, v in enumerate(vals):
            box[i] = v if box[i] is None else (
                min(box[i], v) if i % 2 == 0 else max(box[i], v))
    return None if box[0] is None else (box[0], box[1], box[2], box[3])


def export_svg_ink(swf: str, ids: list[int]) -> dict[int, tuple[float, float, float, float]]:
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(
            ["java", "-jar", str(FFDEC), "-selectid", ",".join(map(str, ids)),
             "-format", "text:svg", "-export", "text", td, swf],
            capture_output=True, text=True, cwd=str(ROOT))
        out: dict[int, tuple[float, float, float, float]] = {}
        for p in Path(td).glob("*.svg"):
            ink = svg_ink(p.read_text(encoding="utf-8"))
            if ink is not None:
                out[int(p.stem)] = ink
        return out


def ink_metrics(font: TTFont, text: str) -> tuple[float, float]:
    """Return (xmin, width) of the text's ink in font units."""
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
        return 0.0, 0.0
    return xmin, xmax - xmin


def advance_units(font: TTFont, text: str) -> float:
    """Total advance width of the text, in font units."""
    cmap = font.getBestCmap()
    hmtx = font["hmtx"].metrics
    upm = font["head"].unitsPerEm
    total = 0.0
    for ch in text:
        g = cmap.get(ord(ch))
        if g is not None:
            total += hmtx[g][0] if g in hmtx else upm
    return total


def parse_formatted(famt: str) -> tuple[str, str, list[tuple[str, str]]]:
    """Split a ``text:formatted`` dump into (tag header, preamble, records).

    A dump looks like ``[tag][rec1]text1[rec2]text2...``.  Returns the tag
    header, the text between the tag header and the first record (normally
    empty) and the list of ``(record header, text)`` pairs.
    """
    parts = re.split(r"\[(.*?)\]", famt, flags=re.S)
    tag = parts[1] if len(parts) > 1 else ""
    preamble = parts[2] if len(parts) > 2 else ""
    records = [(parts[i], parts[i + 1]) for i in range(3, len(parts) - 1, 2)]
    return tag, preamble, records


def build_formatted(tag_header: str, preamble: str,
                    records: list[tuple[str, str]]) -> str:
    out = "[" + tag_header + "]" + preamble
    for header, text in records:
        out += "[" + header + "]" + text
    return out


def header_int(header: str, key: str) -> int | None:
    m = re.search(rf"\n{key} (-?\d+)", header)
    return int(m.group(1)) if m else None


def set_header_int(header: str, key: str, value: int) -> str:
    header = re.sub(rf"\n{key} -?\d+", "", header)
    if not header.endswith("\n"):
        header += "\n"
    return header + f"{key} {value}\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--swf", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--orig", required=True)
    ap.add_argument("--ids", default=",".join(map(str, TARGET_IDS)))
    ap.add_argument("--display-font", default=str(DISPLAY_FONT))
    ap.add_argument("--body-font", default=str(BODY_FONT))
    args = ap.parse_args()

    ids = [int(x) for x in args.ids.split(",") if x.strip()]
    texts = export_formatted(args.orig, ids)
    body_font = TTFont(args.body_font)
    display_font = TTFont(args.display_font)
    font = body_font
    upm = body_font["head"].unitsPerEm
    outdir = ROOT / "work" / "aligned"
    outdir.mkdir(parents=True, exist_ok=True)

    info: dict[int, tuple] = {}
    for sid in ids:
        famt = texts.get(sid, "")
        segs = UI_TRANSLATIONS.get(str(sid))
        if not famt or not segs or "align" in famt or len(segs) != 1:
            continue                      # dynamic / multi-record: leave alone
        info[sid] = (
            famt,
            int(re.search(r"xmin (-?\d+)", famt).group(1)),
            int(re.search(r"xmax (-?\d+)", famt).group(1)),
            int(re.search(r"translatex (-?\d+)", famt).group(1)),
            int(re.search(r"\nheight (\d+)", famt).group(1)),
            segs[0],
        )

    common_centre: dict[int, int] = {}
    for members in COMMON_CENTRE_GROUPS:
        present = [i for i in members if i in info]
        if present:
            # tag bounds are ~20px right of the visual bounds -> shift back
            c = sum((info[i][1] + info[i][2]) // 2 for i in present) // len(present)
            c -= 400
            for i in present:
                common_centre[i] = c

    repl = ["-replace", args.swf, args.out]
    for sid, (famt, xmin, xmax, tx, height, body) in info.items():
        scale = height / upm
        xmin_u, ink_u = ink_metrics(font, body)
        ink_centre_tw = (xmin_u + ink_u / 2) * scale
        centre_tw = common_centre.get(sid, (xmin + xmax) // 2)
        new_tx = int(round(centre_tw - ink_centre_tw))   # put ink centre on the axis
        famt2 = re.sub(r"translatex (-?\d+)", f"translatex {new_tx}", famt)
        famt2 = re.sub(r"\]\s*[^\]]*$", "]" + body, famt2)
        p = outdir / f"{sid}.txt"
        p.write_text(famt2, encoding="utf-8")
        repl += [str(sid), str(p)]
        print(f"  {sid}: {body!r} tx {tx}->{new_tx}")

    # Multi-record labels (e.g. the warning body): the tag keeps its own box, but
    # each record is an independent line whose x offset places it inside that box.
    # Re-centre every line's advance box on the centre of the original English
    # block.  Export from the localised SWF so the records keep their current
    # (CJK) font slot; a formatted dump that names the original Latin font would
    # make FFDec fail to find the Chinese glyphs.
    if MULTI_TARGET_IDS:
        display_upm = display_font["head"].unitsPerEm
        multi_texts = export_formatted(args.swf, MULTI_TARGET_IDS)
        for sid in MULTI_TARGET_IDS:
            famt = multi_texts.get(sid, "")
            segs = UI_TRANSLATIONS.get(str(sid))
            if not famt or not segs or "align" in famt:
                continue
            tag, preamble, records = parse_formatted(famt)
            if len(records) != len(segs):
                continue
            xmin = header_int(tag, "xmin")
            xmax = header_int(tag, "xmax")
            if xmin is None or xmax is None:
                continue
            tx = header_int(tag, "translatex") or 0
            rec_heights = [header_int(h, "height") for h, _ in records]
            tag_h = header_int(tag, "height") or next(
                (h for h in rec_heights if h), None)
            if tag_h is None:
                continue
            centre = (xmin + xmax) / 2
            new_records = []
            for (header, _old), body in zip(records, segs):
                body = body.strip("\r\n")
                height = header_int(header, "height") or tag_h
                adv_tw = advance_units(display_font, body) * height / display_upm
                new_x = int(round(centre - tx - adv_tw / 2))
                new_records.append((set_header_int(header, "x", new_x), body))
            famt2 = build_formatted(tag, preamble, new_records)
            p = outdir / f"{sid}.txt"
            p.write_text(famt2, encoding="utf-8")
            repl += [str(sid), str(p)]
            print(f"  {sid}: re-centred {len(records)} records")

    # Right-anchored labels: shift the Chinese left by exactly the amount its ink
    # overshoots the original English ink, so the right edges line up.  Both inks
    # are measured from FFDec SVGs, which is font-agnostic (the formatted export
    # only reports the stale original geometry).  Exporting the current tag from
    # the localised SWF keeps its CJK font slot, and anchoring on its *current*
    # translatex keeps the pass idempotent.
    if RIGHT_ALIGN_IDS:
        cur = export_formatted(args.swf, RIGHT_ALIGN_IDS)
        orig_fmt = export_formatted(args.orig, RIGHT_ALIGN_IDS)
        orig_ink = export_svg_ink(args.orig, RIGHT_ALIGN_IDS)
        built_ink = export_svg_ink(args.swf, RIGHT_ALIGN_IDS)
        for sid in RIGHT_ALIGN_IDS:
            famt = cur.get(sid, "")
            ofamt = orig_fmt.get(sid, "")
            segs = UI_TRANSLATIONS.get(str(sid))
            o, b = orig_ink.get(sid), built_ink.get(sid)
            if (not famt or not ofamt or not segs or "align" in famt
                    or len(segs) != 1 or not o or not b):
                continue
            tx = header_int(famt, "translatex") or 0
            bxmin = header_int(famt, "xmin"); bxmax = header_int(famt, "xmax")
            bymin = header_int(famt, "ymin"); bymax = header_int(famt, "ymax")
            oxmin = header_int(ofamt, "xmin")
            if None in (bxmin, bxmax, bymin, bymax, oxmin):
                continue
            # Ink box in the tag's own twips (SVG units are tag pixels -> x20),
            # so the measurement survives a change of the stored bounds.
            left = bxmin + b[0] * 20; right = bxmin + b[1] * 20
            top = bymin + b[2] * 20; bottom = bymin + b[3] * 20
            orig_right = oxmin + o[1] * 20
            shift = int(round(right - orig_right))    # twips the Chinese overshoots
            new_tx = tx - shift
            famt2 = re.sub(r"translatex (-?\d+)", f"translatex {new_tx}", famt)
            # The player clips static text to the tag's stored bounds, and the
            # shifted Chinese now extends past the original (generous) box, so
            # widen the bounds to keep the whole glyphs visible.
            famt2 = re.sub(r"(?m)^xmin -?\d+", f"xmin {min(bxmin, int(left - shift) - 20)}", famt2)
            famt2 = re.sub(r"(?m)^xmax -?\d+", f"xmax {max(bxmax, int(right - shift) + 20)}", famt2)
            famt2 = re.sub(r"(?m)^ymin -?\d+", f"ymin {min(bymin, int(top) - 20)}", famt2)
            famt2 = re.sub(r"(?m)^ymax -?\d+", f"ymax {max(bymax, int(bottom) + 20)}", famt2)
            famt2 = re.sub(r"\]\s*[^\]]*$", "]" + segs[0], famt2)
            p = outdir / f"{sid}.txt"
            p.write_text(famt2, encoding="utf-8")
            repl += [str(sid), str(p)]
            print(f"  {sid}: {segs[0]!r} right-aligned tx {tx}->{new_tx} "
                  f"(shift {shift}, box [{min(bxmin, int(left - shift) - 20)},"
                  f"{max(bxmax, int(right - shift) + 20)}])")

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

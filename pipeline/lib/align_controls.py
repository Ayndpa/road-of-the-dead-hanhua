"""Re-align translated UI labels that lost their original alignment.

FFDec's text import lays the shorter Chinese out from the tag's *left* origin, so
labels the original centred (the options list, the panel titles) or right-aligned
(the controls list) come out off-axis once the text is shorter.

This module exports each affected static ``DefineText`` tag in FFDec's
"formatted" form and rewrites its ``translatex`` so the Chinese ink lands on the
original English ink axis:

* ``TARGET_IDS`` - labels that were centred; the Chinese is centred on the
  measured original ink centre.
* ``LIST_CENTER_IDS`` - the controls list, whose original names were right
  aligned on one edge; the Chinese is centred on a single shared column axis
  instead (per the localisation request).
* ``RIGHT_ALIGN_IDS`` - labels kept right-aligned, shifted so the right edges
  line the original English ones up.

Only static tags are touched; dynamic text fields (which carry their own
``align``) are left alone.

Usage:
    python pipeline/lib/align_controls.py --swf <in.swf> --out <out.swf> --orig <orig.swf>
"""
from __future__ import annotations

import argparse
import re
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline.lib.remap_font import Bits, load_swf_raw  # noqa: E402
from pipeline.lib.translations import UI_TRANSLATIONS  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
FFDEC = ROOT / "tools" / "ffdec" / "ffdec-cli.jar"
# The two embedded CJK faces: display = Dirty Ego style (menus/titles/HUD),
# body = serif (Modern No. 20 replacement).  Only the multi-record fallback still
# needs a face by name; the single-record passes measure rendered ink directly.
DISPLAY_FONT = ROOT / "work" / "fonts" / "ui_cjk.ttf"
BODY_FONT = ROOT / "work" / "fonts" / "ui_body.ttf"

# Static single-record UI labels that the original drew centred on a known
# optical axis.  The stored tag bounds are wider than the drawn text (and for
# the options headings the bounds centre sits ~5-20px off the visual centre), so
# the Chinese is centred on the original English *ink* axis measured from an
# FFDec SVG dump, not on the bounds.  Measuring both renders the same way is
# font-agnostic (works for both the serif body face and the Dirty Ego titles)
# and stays correct even when FFDec adds per-pair kerning to the CJK glyphs.
TARGET_IDS = [
    # options panel (sprite 4430)
    4407, 4414, 4424, 4428, 4429, 4408, 4409, 4411, 4412,
    4415, 4416, 4418, 4419, 4421, 4422, 4425, 4426,
    # panel titles ("CONTROLS" / "OPTIONS") - decorative Dirty Ego face
    4403, 4406,
    # warning screen title
    4026,
    # loading screen "click here to play" (PlayButton idle / hover)
    1762, 1763,
]

# Controls list (sprite 4404).  The original English action names were all
# right-aligned on one common edge, which leaves the shorter Chinese hugging the
# key column with a wide gap on the left.  Instead the Chinese is centred on the
# common *column* axis: one screen axis midway between the widest English label's
# left edge and the common right edge, shared by every row.
LIST_CENTER_IDS = [
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
]
LIST_SPRITE_ID = 4404

# Multi-record static labels.  Each record is one drawn line; FFDec re-imports
# them all at the tag's left origin, so the shorter Chinese rows come out ragged.
# Every record is re-centred on the centre of the original English block.
MULTI_TARGET_IDS = [
    4025,  # warning body: three red lines, centred as a block
]

# Labels anchored to the right edge.  The original English was right-aligned and
# the Chinese is imported at the tag's left origin, so it must be shifted to line
# the right edges back up.  These are right-aligned on the original ink, and their
# stored bounds are widened because Flash clips static text to that rect.
RIGHT_ALIGN_IDS = [
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
    # garage bottom-right "Drive To" -> "前往".  The static label sits to the left
    # of the dynamic destination name, so the (shorter) Chinese must hug the
    # destination on its right instead of sitting at the English box's left origin,
    # which left the two characters floating with a gap before the destination.
    4019,  # idle
    4020,  # over
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

    def _grp(i: int) -> tuple[float, float, float, float]:
        # (scaleX, scaleY, translateX, translateY) of the i-th wrapping ``<g>``.
        if i < len(gs):
            v = [float(x) for x in gs[i].split(",")]
            return v[0], v[3], v[4], v[5]
        return 1.0, 1.0, 0.0, 0.0

    # The outer group shifts the tag bounds; the inner one is the text matrix.
    # The matrix scale (FFDec's ``scalexf``/``scaleyf``) has to be folded in or a
    # horizontally stretched run is measured at its unstretched width.
    a0, d0, e0, f0 = _grp(0)
    a1, d1, e1, f1 = _grp(1)
    gxs, gys = a0 * a1, d0 * d1
    gx, gy = e0 + a0 * e1, f0 + d0 * f1
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
        vals = (gx + gxs * (ex + sx * bounds[0]),
                gx + gxs * (ex + sx * bounds[1]),
                gy + gys * (ey + sy * bounds[2]),
                gy + gys * (ey + sy * bounds[3]))
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


def export_svg_raw(swf: str, ids: list[int]) -> dict[int, str]:
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(
            ["java", "-jar", str(FFDEC), "-selectid", ",".join(map(str, ids)),
             "-format", "text:svg", "-export", "text", td, swf],
            capture_output=True, text=True, cwd=str(ROOT))
        return {int(p.stem): p.read_text(encoding="utf-8")
                for p in Path(td).glob("*.svg")}


def sprite_placements(swf: str, sprite_id: int) -> dict[int, tuple[float, float]]:
    """Direct children of ``sprite_id`` as ``char id -> (translateX twips, scaleX)``.

    A static text record stores its own ``translatex`` in the tag, so an SVG ink
    measured for that tag is relative to its own text matrix.  Comparing several
    tags on screen (the controls list shares one column axis) therefore needs the
    tag's placement matrix inside the sprite as well.
    """
    data, _ = load_swf_raw(swf)
    pos = 8
    nbits = data[pos] >> 3
    pos += (5 + nbits * 4 + 7) // 8
    pos += 4
    while pos < len(data):
        code_len = struct.unpack_from("<H", data, pos)[0]
        p = pos + 2
        code = code_len >> 6
        length = code_len & 0x3F
        if length == 0x3F:
            length = struct.unpack_from("<I", data, p)[0]
            p += 4
        body = data[p : p + length]
        if (code == 39 and len(body) >= 4
                and struct.unpack_from("<H", body, 0)[0] == sprite_id):
            return _sprite_children(body)
        pos = p + length
    return {}


def _sprite_children(body: bytes) -> dict[int, tuple[float, float]]:
    out: dict[int, tuple[float, float]] = {}
    pos = 4                       # skip the sprite's char id + frame count
    while pos < len(body):
        code_len = struct.unpack_from("<H", body, pos)[0]
        pos += 2
        code = code_len >> 6
        length = code_len & 0x3F
        if length == 0x3F:
            length = struct.unpack_from("<I", body, pos)[0]
            pos += 4
        tb = body[pos : pos + length]
        pos += length
        if code != 26 or len(tb) < 5:        # PlaceObject2 only
            continue
        flags = tb[0]
        if not flags & 0x02 or not flags & 0x04:
            continue                          # needs a character + a matrix
        cid = struct.unpack_from("<H", tb, 3)[0]
        b = Bits(tb, 5)
        sx = 1.0
        if b.u(1):
            n = b.u(5)
            sx = b.si(n) / 65536.0
            b.si(n)
        if b.u(1):
            n = b.u(5)
            b.si(n)
            b.si(n)
        n = b.u(5)
        tx = b.si(n)
        out[cid] = (float(tx), sx)
    return out


def svg_line_boxes(txt: str) -> list[tuple[float, float]]:
    """Per-line ink boxes ``(left, right)`` of an FFDec ``text:svg`` dump.

    The dump renders every record (line) in one coordinate space, so glyphs are
    grouped by their vertical placement; this survives per-record kerning /
    letterspacing that the ``formatted`` geometry does not reflect.
    """
    glyphs: dict[str, tuple[float, float]] = {}
    for m in re.finditer(r'<g id="([^"]+)">\s*<path d="([^"]+)"', txt):
        xs = [float(v) for v in _NUM.findall(m.group(2))][0::2]
        if xs:
            glyphs[m.group(1)] = (min(xs), max(xs))
    gs = re.findall(r'<g transform="matrix\(([^)]*)\)"', txt)[:2]
    a0 = float(gs[0].split(",")[0]) if gs else 1.0
    e0 = float(gs[0].split(",")[4]) if gs else 0.0
    a1 = float(gs[1].split(",")[0]) if len(gs) > 1 else 1.0
    e1 = float(gs[1].split(",")[4]) if len(gs) > 1 else 0.0
    gxs = a0 * a1
    gx = e0 + a0 * e1
    lines: dict[int, list[float]] = {}
    for use in re.findall(r'<use\b[^>]*>', txt):
        m = re.search(r'transform="matrix\(([^)]*)\)"', use)
        href = re.search(r'xlink:href="#([^"]+)"', use)
        if not m or not href:
            continue
        nums = [float(v) for v in m.group(1).split(",")]
        sx, ex, ey = nums[0], nums[4], nums[5]
        b = glyphs.get(href.group(1))
        if b is None:
            continue
        left = gx + gxs * (ex + sx * b[0])
        right = gx + gxs * (ex + sx * b[1])
        d = lines.setdefault(round(ey / 10), [None, None])  # type: ignore[arg-type]
        d[0] = left if d[0] is None else min(d[0], left)
        d[1] = right if d[1] is None else max(d[1], right)
    return [(v[0], v[1]) for _k, v in sorted(lines.items())]


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


def widen_bounds(famt: str, bxmin: int, bxmax: int, bymin: int, bymax: int,
                 ink_left: float, ink_right: float,
                 ink_top: float, ink_bottom: float, pad: int = 20) -> str:
    """Grow the tag's stored clip rect to enclose the (moved) ink.

    Flash clips static ``DefineText`` to ``xmin/xmax/ymin/ymax``.  The original
    bounds hug the English text; centring the shorter Chinese moves it left of
    the old ``xmin`` (or right of ``xmax``) and the glyphs get cut, so the rect is
    widened to the new ink box plus ``pad`` twips.
    """
    famt = re.sub(r"(?m)^xmin -?\d+", f"xmin {min(bxmin, int(ink_left) - pad)}", famt)
    famt = re.sub(r"(?m)^xmax -?\d+", f"xmax {max(bxmax, int(ink_right) + pad)}", famt)
    famt = re.sub(r"(?m)^ymin -?\d+", f"ymin {min(bymin, int(ink_top) - pad)}", famt)
    famt = re.sub(r"(?m)^ymax -?\d+", f"ymax {max(bymax, int(ink_bottom) + pad)}", famt)
    return famt


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
    display_font = TTFont(args.display_font)
    outdir = ROOT / "work" / "aligned"
    outdir.mkdir(parents=True, exist_ok=True)

    centre_ids = [i for i in ids if str(i) in UI_TRANSLATIONS]
    repl = ["-replace", args.swf, args.out]

    # Single-record labels centred on the original English ink axis.  Both the
    # original and the localised renders are measured from SVG dumps, so the
    # comparison lives in the tag's own text-matrix space and is unaffected by
    # the stored bounds, the font face or FFDec's CJK kerning.  Anchoring on the
    # tag's *current* translatex keeps the pass idempotent.
    if centre_ids:
        cur = export_formatted(args.swf, centre_ids)
        orig_fmt = export_formatted(args.orig, centre_ids)
        orig_ink = export_svg_ink(args.orig, centre_ids)
        built_ink = export_svg_ink(args.swf, centre_ids)
        for sid in centre_ids:
            famt = cur.get(sid, "")
            ofamt = orig_fmt.get(sid, "")
            segs = UI_TRANSLATIONS[str(sid)]
            o, b = orig_ink.get(sid), built_ink.get(sid)
            if (not famt or not ofamt or "align" in famt
                    or len(segs) != 1 or o is None or b is None):
                continue                  # dynamic / multi-record: leave alone
            bxmin = header_int(famt, "xmin")
            bxmax = header_int(famt, "xmax")
            bymin = header_int(famt, "ymin")
            bymax = header_int(famt, "ymax")
            oxmin = header_int(ofamt, "xmin")
            tx = header_int(famt, "translatex")
            if None in (bxmin, bxmax, bymin, bymax, oxmin, tx):
                continue
            desired = oxmin + (o[0] + o[1]) / 2 * 20   # original English ink axis
            built_c = bxmin + (b[0] + b[1]) / 2 * 20   # current Chinese ink axis
            new_tx = int(round(tx - (built_c - desired)))
            s = new_tx - tx
            famt2 = re.sub(r"translatex (-?\d+)", f"translatex {new_tx}", famt)
            famt2 = re.sub(r"\]\s*[^\]]*$", "]" + segs[0], famt2)
            famt2 = widen_bounds(famt2, bxmin, bxmax, bymin, bymax,
                                 bxmin + b[0] * 20 + s, bxmin + b[1] * 20 + s,
                                 bymin + b[2] * 20, bymin + b[3] * 20)
            p = outdir / f"{sid}.txt"
            p.write_text(famt2, encoding="utf-8")
            repl += [str(sid), str(p)]
            print(f"  {sid}: {segs[0]!r} centred tx {tx}->{new_tx}")

    # Controls list: centre every row on the common column axis.  The original
    # English names were right-aligned on one edge, so the axis is the midpoint
    # of the union of their on-stage ink; each row is put there individually via
    # its placement matrix inside the sprite (the rows use different placements).
    if LIST_CENTER_IDS:
        place = sprite_placements(args.orig, LIST_SPRITE_ID)
        list_ids = [i for i in LIST_CENTER_IDS if str(i) in UI_TRANSLATIONS]
        ofmt = export_formatted(args.orig, list_ids)
        bfmt = export_formatted(args.swf, list_ids)
        oink = export_svg_ink(args.orig, list_ids)
        bink = export_svg_ink(args.swf, list_ids)
        boxes: list[tuple[float, float]] = []
        for sid in list_ids:
            t = place.get(sid)
            o = oink.get(sid)
            oxmin = header_int(ofmt.get(sid, ""), "xmin")
            if t is None or o is None or oxmin is None:
                continue
            sp_tx, sp_s = t
            boxes.append((sp_tx + sp_s * (oxmin + o[0] * 20),
                          sp_tx + sp_s * (oxmin + o[1] * 20)))
        if boxes:
            axis = (min(lo for lo, _ in boxes) + max(hi for _, hi in boxes)) / 2
            for sid in list_ids:
                famt = bfmt.get(sid, "")
                b = bink.get(sid)
                t = place.get(sid)
                if not famt or "align" in famt or b is None or t is None:
                    continue
                bxmin = header_int(famt, "xmin")
                bxmax = header_int(famt, "xmax")
                bymin = header_int(famt, "ymin")
                bymax = header_int(famt, "ymax")
                btx = header_int(famt, "translatex")
                if None in (bxmin, bxmax, bymin, bymax, btx):
                    continue
                sp_tx, sp_s = t
                built_tl = bxmin + (b[0] + b[1]) / 2 * 20   # Chinese ink axis (tag)
                want_tl = (axis - sp_tx) / sp_s             # common axis in tag space
                new_tx = int(round(btx - (built_tl - want_tl)))
                s = new_tx - btx
                famt2 = re.sub(r"translatex (-?\d+)", f"translatex {new_tx}", famt)
                text = UI_TRANSLATIONS[str(sid)][0]
                famt2 = re.sub(r"\]\s*[^\]]*$", "]" + text, famt2)
                famt2 = widen_bounds(famt2, bxmin, bxmax, bymin, bymax,
                                     bxmin + b[0] * 20 + s, bxmin + b[1] * 20 + s,
                                     bymin + b[2] * 20, bymin + b[3] * 20)
                p = outdir / f"{sid}.txt"
                p.write_text(famt2, encoding="utf-8")
                repl += [str(sid), str(p)]
                print(f"  {sid}: {text!r} centred tx {btx}->{new_tx}")

    # Multi-record labels (e.g. the warning body): the tag keeps its own box, but
    # each record is an independent line whose x offset places it inside that box.
    # Centre every line's *rendered ink* on the original English block's optical
    # axis.  The formatted advance box misses full-width CJK punctuation («《»,
    # trailing «。») and any per-record letterspacing FFDec emits, so the actual
    # renders are measured from SVG dumps instead; each record's x is a pure
    # translation, so shifting it by the measured delta re-centres the line.
    if MULTI_TARGET_IDS:
        display_upm = display_font["head"].unitsPerEm
        multi_texts = export_formatted(args.swf, MULTI_TARGET_IDS)
        built_svg = export_svg_raw(args.swf, MULTI_TARGET_IDS)
        orig_svg = export_svg_raw(args.orig, MULTI_TARGET_IDS)
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
            orig_lines = svg_line_boxes(orig_svg.get(sid, ""))
            built_lines = svg_line_boxes(built_svg.get(sid, ""))
            use_ink = bool(orig_lines) and len(built_lines) == len(records)
            if use_ink:
                axis = sum((l + r) / 2 for l, r in orig_lines) / len(orig_lines)
            else:
                centre = (xmin + xmax) / 2   # fallback: advance box in the tag
            new_records = []
            for i, ((header, _old), body) in enumerate(zip(records, segs)):
                body = body.strip("\r\n")
                if use_ink:
                    bl, br = built_lines[i]
                    shift = int(round((axis - (bl + br) / 2) * 20))
                    new_x = (header_int(header, "x") or 0) + shift
                else:
                    height = header_int(header, "height") or tag_h
                    adv_tw = advance_units(display_font, body) * height / display_upm
                    new_x = int(round(centre - tx - adv_tw / 2))
                new_records.append((set_header_int(header, "x", new_x), body))
            famt2 = build_formatted(tag, preamble, new_records)
            p = outdir / f"{sid}.txt"
            p.write_text(famt2, encoding="utf-8")
            repl += [str(sid), str(p)]
            print(f"  {sid}: re-centred {len(records)} records "
                  f"({'ink' if use_ink else 'advance'})")

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

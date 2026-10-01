"""Build the fully localised SWF: Chinese UI text + Chinese subtitles.

The decorative title face (font id 20, "Dirty Ego") is never touched: the logo,
credits names and HUD numerals keep their original design.  Only the texts that
actually become Chinese are repointed to a spare font slot that receives a CJK
face.
"""
from __future__ import annotations

import argparse
import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from align_controls import build_formatted, export_formatted, parse_formatted  # noqa: E402
from remap_font import edit_text_font_offset, load_swf_raw, text_font_offsets  # noqa: E402
from ui_text import UI_TRANSLATIONS  # noqa: E402

FFDEC = ROOT / "tools" / "ffdec" / "ffdec-cli.jar"
ORIG = ROOT / "dist" / "Road-Of-The-Dead.swf"
RECORDSEP = "--- RECORDSEPARATOR ---"


def texts_using_font(swf: str, font_id: int) -> set[int]:
    data, _ = load_swf_raw(swf)
    buf = data
    pos = 8
    nbits = buf[pos] >> 3
    pos += (5 + nbits * 4 + 7) // 8
    pos += 4
    found: set[int] = set()
    while pos < len(buf):
        code_len = struct.unpack_from("<H", buf, pos)[0]
        p = pos + 2
        code = code_len >> 6
        length = code_len & 0x3F
        if length == 0x3F:
            length = struct.unpack_from("<I", buf, p)[0]
            p += 4
        body = buf[p : p + length]
        if code in (11, 33) and len(body) >= 2:
            cid = struct.unpack_from("<H", body, 0)[0]
            if any(struct.unpack_from("<H", body, o)[0] == font_id
                   for o in text_font_offsets(body, code)):
                found.add(cid)
        elif code == 37 and len(body) >= 2:
            cid = struct.unpack_from("<H", body, 0)[0]
            off = edit_text_font_offset(body)
            if off is not None and struct.unpack_from("<H", body, off)[0] == font_id:
                found.add(cid)
        pos = p + length
    return found


def text_tag_fonts(swf: str) -> dict[int, tuple[bool, set[int]]]:
    """char id -> (is_edittext, fonts) for DefineText/2/EditText tags."""
    data, _ = load_swf_raw(swf)
    buf = data
    pos = 8
    nbits = buf[pos] >> 3
    pos += (5 + nbits * 4 + 7) // 8
    pos += 4
    out: dict[int, tuple[bool, set[int]]] = {}
    while pos < len(buf):
        code_len = struct.unpack_from("<H", buf, pos)[0]
        p = pos + 2
        code = code_len >> 6
        length = code_len & 0x3F
        if length == 0x3F:
            length = struct.unpack_from("<I", buf, p)[0]
            p += 4
        body = buf[p : p + length]
        if code in (11, 33) and len(body) >= 2:
            cid = struct.unpack_from("<H", body, 0)[0]
            out[cid] = (False, {struct.unpack_from("<H", body, o)[0]
                                for o in text_font_offsets(body, code)})
        elif code == 37 and len(body) >= 2:
            cid = struct.unpack_from("<H", body, 0)[0]
            off = edit_text_font_offset(body)
            out[cid] = (True, {struct.unpack_from("<H", body, off)[0]} if off else set())
        pos = p + length
    return out


def export_plain_texts(swf: str) -> dict[int, list[str]]:
    """Text of every static/edited text tag, split into records."""
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(["java", "-Xmx4g", "-jar", str(FFDEC),
                        "-export", "text", td, swf],
                       capture_output=True, text=True, cwd=str(ROOT))
        out: dict[int, list[str]] = {}
        for p in Path(td).glob("*.txt"):
            parts = [s.strip() for s in p.read_text(encoding="utf-8").split(RECORDSEP)]
            out[int(p.stem)] = [s for s in parts if s]
        return out


def make_formatted_text(dump: str, segs: list[str], slot: int) -> str | None:
    """Formatted import text for one tag: drop kerning, force the CJK font slot.

    FFDec's plain text import round-trips the tag's existing kerning through a
    formatted dump.  That kerning only references the original Latin pairs, but
    the import still bakes an uneven per-record ``letterspacing`` out of it,
    which horizontally squeezes the translated CJK glyphs (the garage tooltips
    visibly compress mid-line).  A spacing key that cannot be represented at all
    (a double quote, an empty character) goes further and aborts the parse,
    leaving the tag with the previous glyph indices, which then decode through
    the new font as garbage.  Re-importing as a formatted dump with every
    spacing entry removed fixes both: the glyphs advance naturally.
    """
    if "spacing" not in dump and "letterspacing" not in dump:
        return None
    tag, pre, records = parse_formatted(dump)
    if not segs or len(records) != len(segs):
        return None
    new_records = []
    for (hdr, _old), text in zip(records, segs):
        keep = [ln for ln in hdr.splitlines()
                if not ln.strip().startswith(("spacing", "letterspacing", "font"))]
        h = "\n".join(keep)
        if not h.endswith("\n"):
            h += "\n"
        h += f"font {slot}\n"
        new_records.append((h, text.strip("\r\n")))
    return build_formatted(tag, pre, new_records)


def run(args: list[str]) -> None:
    proc = subprocess.run(args, capture_output=True, text=True)
    if proc.returncode != 0:
        print("\n".join(proc.stdout.splitlines()[-15:]))
        print(proc.stderr[-3000:], file=sys.stderr)
        raise SystemExit(f"ffdec failed with {proc.returncode}")
    for ln in [x for x in proc.stdout.splitlines() if x.strip()][-2:]:
        print("   ", ln)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--orig", default=str(ORIG))
    ap.add_argument("--out", default=str(ROOT / "dist" / "rotl-zh-full.swf"))
    ap.add_argument("--texts", default=str(ROOT / "work" / "ui_texts"))
    ap.add_argument("--display-font", default=str(ROOT / "work" / "fonts" / "ui_cjk.ttf"))
    ap.add_argument("--body-font", default=str(ROOT / "work" / "fonts" / "ui_body.ttf"))
    ap.add_argument("--decor-font-id", type=int, default=20)
    # Spare slots that receive the two CJK faces.  Both must be slots whose
    # *original* DefineFont has a layout (advance) table: FFDec keeps that tag's
    # HasLayout flag when it swaps the glyphs, and a DefineEditText lays its text
    # out from the referenced font's advances.  A layout-less slot (e.g. 88) makes
    # every dynamic string (the garage "Drive To <city>" line, tooltips, HUD
    # counters, ...) collapse to zero width and vanish.  92 is a free, layout-
    # capable Verdana slot.
    ap.add_argument("--display-font-id", type=int, default=92)
    ap.add_argument("--body-font-id", type=int, default=22)
    ap.add_argument(
        "--body-font-ids",
        default="22,26,32,46,87,88,94,558,1103,1106,1758,2819,4013",
    )
    args = ap.parse_args()

    all_texts = {int(p.stem) for p in Path(args.texts).glob("*.txt")}
    translated = {int(k) for k in UI_TRANSLATIONS if int(k) in all_texts}

    # The original uses two faces: Dirty Ego (font 20) for menus/HUD/titles and
    # Modern No. 20 (font 22) for body text.  Font 20 is shared with the logo, so
    # it is never replaced; only the *translated* font-20 tags are moved to the
    # display slot.  Everything else lands on the single body slot.
    tagfonts = text_tag_fonts(args.orig)
    decor = texts_using_font(args.orig, args.decor_font_id)
    display_ids = sorted(decor & translated)
    body_src = {int(x) for x in args.body_font_ids.split(",") if x.strip()}
    # Only *translated* tags may be repointed: a DefineText stores glyph-table
    # indices, so changing its font without re-importing the text reinterprets
    # the old indices through the new font and garbles it.  Untranslated tags
    # keep their original (replaced or not) font and text verbatim.
    body_ids = sorted(
        cid for cid, (_is_edit, fonts) in tagfonts.items()
        if fonts & body_src and cid not in set(display_ids) and cid in translated
    )
    print(f"display: font {args.decor_font_id} -> slot {args.display_font_id}, "
          f"{len(display_ids)} texts")
    print(f"body: fonts {sorted(body_src)} -> slot {args.body_font_id}, "
          f"{len(body_ids)} texts")

    (ROOT / "work").mkdir(parents=True, exist_ok=True)
    (ROOT / "dist").mkdir(parents=True, exist_ok=True)
    remap = ROOT / "pipeline" / "remap_font.py"
    base1 = ROOT / "work" / "base_remap1.swf"
    base = ROOT / "work" / "base_remap.swf"
    run([
        "uv", "run", "python", str(remap), args.orig, str(base1),
        "--old", str(args.decor_font_id),
        "--new", str(args.display_font_id),
        "--only", ",".join(str(x) for x in display_ids),
    ])
    run([
        "uv", "run", "python", str(remap), str(base1), str(base),
        "--old", ",".join(str(x) for x in sorted(body_src)),
        "--new", str(args.body_font_id),
        "--only", ",".join(str(x) for x in body_ids),
    ])

    texts = {int(p.stem): p for p in Path(args.texts).glob("*.txt")
             if int(p.stem) in translated}
    print(f"text tags to import: {len(texts)} (translated only)")

    tmp_ui = ROOT / "work" / "build_ui.swf"
    tmp_sub = ROOT / "dist" / "build_sub.swf"

    # Replace only the two CJK slots, so each face is embedded once: font 92 is
    # the Dirty Ego style, font 22 the serif body face.
    repl = ["-replace", str(base), str(tmp_ui),
            str(args.display_font_id), args.display_font,
            str(args.body_font_id), args.body_font]
    for cid in sorted(texts):
        repl += [str(cid), str(texts[cid])]
    run(["java", "-Xmx4g", "-jar", str(FFDEC), *repl])

    # Second, formatted import for the tags whose plain import kept the original
    # kerning: either it could not round-trip (the tag's glyph indices are left
    # pointing at the old font and decode as garbage), or it succeeded but baked
    # the Latin kerning into an uneven per-record letterspacing that squeezes the
    # CJK glyphs.  Both are detected from a formatted dump of the imported tags
    # and re-imported with the spacing dropped and the font forced to the CJK
    # slot.  Doing it for the whole tag set in one pass keeps the glyph advances
    # natural and, unlike the old plain-only import, also fixes the horizontal
    # compression.
    got = export_plain_texts(str(tmp_ui))
    failed = [cid for cid in sorted(translated)
              if [s.strip() for s in UI_TRANSLATIONS[str(cid)] if s.strip()]
              != got.get(cid, [])]
    dumps = export_formatted(str(tmp_ui), sorted(translated)) if translated else {}
    spaced = [cid for cid in sorted(translated)
              if cid not in failed
              and ("spacing" in dumps.get(cid, "")
                   or "letterspacing" in dumps.get(cid, ""))]
    fix_ids = sorted(set(failed) | set(spaced))
    if fix_ids:
        print(f"re-importing {len(fix_ids)} kerning tags "
              f"(garbled={len(failed)}, squeezed={len(spaced)})")
        fmtdir = ROOT / "work" / "fmt_texts"
        fmtdir.mkdir(parents=True, exist_ok=True)
        fixed = ROOT / "work" / "build_ui_fixed.swf"
        fix = ["-replace", str(tmp_ui), str(fixed)]
        for cid in fix_ids:
            slot = (args.display_font_id if cid in set(display_ids)
                    else args.body_font_id)
            text = make_formatted_text(dumps.get(cid, ""),
                                       UI_TRANSLATIONS[str(cid)], slot)
            if text is not None:
                p = fmtdir / f"{cid}.txt"
                p.write_text(text, encoding="utf-8")
                fix += [str(cid), str(p)]
        if len(fix) > 3:
            run(["java", "-Xmx4g", "-jar", str(FFDEC), *fix])
            tmp_ui = fixed

    as3_dir = ROOT / "patch" / "as3"
    repl2 = ["-replace", str(tmp_ui), str(tmp_sub), "DTSound", str(ROOT / "patch" / "DTSound.as")]
    for p in sorted(as3_dir.glob("*.as")):
        repl2 += [p.stem, str(p)]
    run(["java", "-Xmx4g", "-jar", str(FFDEC), *repl2])

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp_menu = tmp_sub.with_name("tmp_menu.swf")
    run([
        "uv", "run", "python", str(ROOT / "pipeline" / "menu_labels.py"),
        "--swf", str(tmp_sub), "--out", str(tmp_menu), "--orig", args.orig,
    ])
    run([
        "uv", "run", "python", str(ROOT / "pipeline" / "align_controls.py"),
        "--swf", str(tmp_menu), "--out", str(out), "--orig", args.orig,
    ])
    print(f"built {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

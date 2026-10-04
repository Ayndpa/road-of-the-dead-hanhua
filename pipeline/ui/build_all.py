"""Build the fully localised SWF: Chinese UI text + Chinese subtitles.

ROTD1 ships more than the two faces the old build assumed: besides Dirty Ego
(20, menus/HUD/titles) and Modern No. 20 (22, body prose) the UI uses Arial
(26/32/1758), Arial Black (46/558), Verdana (87/88/94), Arial Narrow (4013),
FFF Calypso (1103) and FFF Business Bold (1106).  Each translated face keeps its
own visual role instead of every body font collapsing into one serif slot:

    original face            slot   CJK face
    Dirty Ego        20       92    RoadOfTheDeadCN  (display)
    Modern No. 20    22       22    Noto Serif SC    (serif body)
    Arial/Verdana/Narrow  26/32/87/88/94/4013
                              94    Noto Sans SC     (sans)
    FFF Calypso/Business Bold  1103/1106
                            1106    Noto Sans SC Bold
    Arial Black      46/558 1758    Noto Sans SC Black

Font 20 is shared with the logo, so it is never replaced: only its *translated*
tags move to the display slot.  Every tag that lands on a repurposed slot is
re-imported (translated or not), otherwise its stale glyph indices decode
through the CJK face as garbage.  The finished SWF is zlib-compressed (CWS) like
the shipped game.
"""
from __future__ import annotations

import argparse
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline.lib.align_controls import build_formatted, export_formatted, parse_formatted  # noqa: E402
from pipeline.lib.remap_font import (  # noqa: E402
    Bits,
    clear_font_style,
    edit_text_font_offset,
    load_swf_raw,
    text_font_offsets,
)
from pipeline.lib.translations import UI_TRANSLATIONS  # noqa: E402

FFDEC = ROOT / "tools" / "ffdec" / "ffdec-cli.jar"
ORIG = ROOT / "dist" / "Road-Of-The-Dead.swf"
RECORDSEP = "--- RECORDSEPARATOR ---"

# --- font adaptation map (see module docstring) -----------------------------
G1_FONT_MAP: dict[int, int] = {
    20: 92, 22: 22, 94: 94, 1106: 1106,
    26: 94, 32: 94, 87: 94, 88: 94, 4013: 94,
    1103: 1106,
    46: 1758, 558: 1758,
}
G1_SLOT_FACE: dict[int, str] = {
    92: "display", 22: "serif", 94: "sans", 1106: "sans_bold", 1758: "sans_black",
}
G1_REPLACED: set[int] = set(G1_SLOT_FACE)
# Subset file names: display/serif keep the names menu_labels.py and
# align_controls.py load by default.
G1_SLOT_SUBSET: dict[int, str] = {
    92: "ui_cjk.ttf", 22: "ui_body.ttf", 94: "ui_sans.ttf",
    1106: "ui_sans_bold.ttf", 1758: "ui_sans_black.ttf",
}
G1_FACE_SOURCE: dict[str, tuple[str, object]] = {
    "display": ("ttf", ROOT / "data" / "fonts" / "RoadOfTheDeadCN.ttf"),
    "serif": ("ttf", ROOT / "data" / "fonts" / "NotoSerifSC-SemiBold.ttf"),
    "sans": ("wght", 400), "sans_bold": ("wght", 700), "sans_black": ("wght", 900),
}
SUBSET_OPTS = ["--no-hinting", "--desubroutinize",
               "--drop-tables+=DSIG,GSUB,GPOS,GDEF,BASE,STAT,gasp,vhea,vmtx"]


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


def formatted_import(dump: str, segs: list[str], slot: int) -> str | None:
    """Rebuild a truncated static tag's formatted text with translated records.

    ``make_formatted_text`` early-outs when the dump has no spacing pairs; the
    initial import needs the same record-by-record rebuild unconditionally.
    """
    if not dump or not segs:
        return None
    tag, pre, records = parse_formatted(dump)
    if len(records) != len(segs):
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


def _empty_records(body: bytes, code: int) -> bytes | None:
    """Keep every record's style (font/x/y/height) but drop all its glyphs."""
    b = Bits(body, 2)
    b.rect()
    b.matrix()
    b.byte += 2                       # glyphBits, advanceBits
    header_end = b.byte
    records = bytearray()
    while b.byte < len(body):
        flags = body[b.byte]
        first = (flags >> 7) & 1
        has_font = bool(flags & 0x08)
        has_color = bool(flags & 0x04)
        has_y = bool(flags & 0x02)
        has_x = bool(flags & 0x01)
        if not (has_font or has_color or has_x or has_y) and first == 0:
            break
        rec_start = b.byte
        b.byte += 1
        if has_font:
            b.byte += 2
        if has_color:
            b.byte += 4 if code == 33 else 3
        if has_x:
            b.byte += 2
        if has_y:
            b.byte += 2
        if has_font:
            b.byte += 2
        count_off = b.byte
        count = body[count_off]
        b.byte += 1
        if has_font or has_color or has_x or has_y or first:
            records += body[rec_start:count_off] + b"\x00"   # glyphCount 0
        if count:
            gb = body[header_end - 2]
            ab = body[header_end - 1]
            b.byte += (count * (gb + ab) + 7) // 8
    if not records:
        return None
    return body[:header_end] + bytes(records) + b"\x00"


def truncate_static_texts(infile: str, outfile: str, ids: set[int]) -> int:
    """Reduce each given static DefineText tag to empty records.

    FFDec's font import remaps every existing text tag's glyphs onto the new
    face by character; a face whose glyphs have no Unicode mapping makes FFDec
    assign indices past the new font's table, which overflows ``glyphToChar``
    and aborts the whole import.  Emptying the tags first leaves nothing to
    remap, and their record count/style are kept so the formatted import can
    rebuild each line in place.
    """
    from pipeline.lib.remap_font import write_swf_fws

    data, _ = load_swf_raw(infile)
    buf = data
    pos = 8
    nbits = buf[pos] >> 3
    pos += (5 + nbits * 4 + 7) // 8
    pos += 4
    out = bytearray(buf[:pos])
    changed = 0
    while pos < len(buf):
        code_len = struct.unpack_from("<H", buf, pos)[0]
        p = pos + 2
        code = code_len >> 6
        length = code_len & 0x3F
        if length == 0x3F:
            length = struct.unpack_from("<I", buf, p)[0]
            p += 4
        body = bytes(buf[p : p + length])
        new_body = None
        if code in (11, 33) and len(body) >= 2:
            if struct.unpack_from("<H", body, 0)[0] in ids:
                new_body = _empty_records(body, code)
                if new_body is not None:
                    changed += 1
        if new_body is None:
            out += buf[pos : p + length]
        elif len(new_body) < 0x3F:
            out += struct.pack("<H", (code << 6) | len(new_body)) + new_body
        else:
            out += (struct.pack("<H", (code << 6) | 0x3F)
                    + struct.pack("<I", len(new_body)) + new_body)
        pos = p + length
    write_swf_fws(bytes(out), outfile)
    return changed


def run(args: list[str]) -> None:
    proc = subprocess.run(args, capture_output=True, text=True)
    if proc.returncode != 0:
        print("\n".join(proc.stdout.splitlines()[-15:]))
        print(proc.stderr[-3000:], file=sys.stderr)
        raise SystemExit(f"ffdec failed with {proc.returncode}")
    for ln in [x for x in proc.stdout.splitlines() if x.strip()][-2:]:
        print("   ", ln)


def face_source_ttf(face: str) -> Path:
    """The source TTF for a face, instancing the Noto Sans SC variable font."""
    kind, val = G1_FACE_SOURCE[face]
    if kind != "wght":
        return Path(val)  # type: ignore[arg-type]
    vf = ROOT / "data" / "fonts" / "NotoSansSC-VF.ttf"
    if not vf.exists():
        raise SystemExit(f"missing {vf} -- run: pwsh -File pipeline/tools/fetch-fonts.ps1")
    out = ROOT / "work" / "fonts" / f"NotoSansSC-{val}.ttf"
    if not out.exists() or out.stat().st_mtime < vf.stat().st_mtime:
        from fontTools.ttLib import TTFont
        from fontTools.varLib import instancer
        f = TTFont(str(vf))
        instancer.instantiateVariableFont(
            f, {"wght": int(val)}, inplace=True, updateFontNames=True)
        f.save(str(out))
    return out


def subset(src: Path, dst: Path, chars: set[str]) -> None:
    charset = dst.with_suffix(".charset.txt")
    charset.write_text("".join(sorted(chars)), encoding="utf-8")
    run(["uv", "run", "pyftsubset", str(src), f"--text-file={charset}",
         f"--output-file={dst}", *SUBSET_OPTS])


def compress_swf(path: str, level: int = 9) -> int:
    """Rewrite an uncompressed (FWS) SWF as zlib-compressed (CWS)."""
    data = Path(path).read_bytes()
    if data[:3] == b"CWS":
        return len(data)
    if data[:3] != b"FWS":
        raise SystemExit(f"{path}: not an FWS uncompressed SWF")
    out = b"CWS" + data[3:4] + len(data).to_bytes(4, "little") + zlib.compress(data[8:], level)
    Path(path).write_bytes(out)
    return len(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--orig", default=str(ORIG))
    ap.add_argument("--out", default=str(ROOT / "dist" / "rotd-zh.swf"))
    ap.add_argument("--texts", default=str(ROOT / "work" / "ui_texts"))
    ap.add_argument("--orig-texts", default=str(ROOT / "work" / "scripts" / "texts"))
    args = ap.parse_args()

    work_texts = {int(p.stem): p for p in Path(args.texts).glob("*.txt")}
    orig_texts = {int(p.stem): p for p in Path(args.orig_texts).glob("*.txt")}
    translated = {int(k) for k in UI_TRANSLATIONS if int(k) in work_texts}

    tagfonts = text_tag_fonts(args.orig)

    def slot_of(cid: int) -> int | None:
        for f in tagfonts.get(cid, (False, set()))[1]:
            if f in G1_FONT_MAP:
                return G1_FONT_MAP[f]
        return None

    font_tags: dict[int, list[int]] = {}
    for cid, (_is_edit, fonts) in tagfonts.items():
        for f in fonts:
            font_tags.setdefault(f, []).append(cid)

    (ROOT / "work").mkdir(parents=True, exist_ok=True)
    (ROOT / "dist").mkdir(parents=True, exist_ok=True)
    tmp_ui = ROOT / "work" / "build_ui.swf"
    # Intermediates stay under work/ (gitignored); dist/ holds only the game
    # originals and the finished localised SWF.
    tmp_sub = ROOT / "work" / "build_sub.swf"
    remap = ROOT / "pipeline" / "lib" / "remap_font.py"

    # --- repoint translated tags onto their face's slot ---------------------
    cur = args.orig
    groups: dict[int, list[int]] = {}
    for f, target in G1_FONT_MAP.items():
        if target != f:
            groups.setdefault(target, []).append(f)
    for target, srcs in sorted(groups.items()):
        tags = sorted({cid for f in srcs for cid in font_tags.get(f, [])
                       if cid in translated})
        if not tags:
            continue
        out = ROOT / "work" / f"remap_{'_'.join(map(str, srcs))}_to_{target}.swf"
        run(["uv", "run", "python", str(remap), str(cur), str(out),
             "--old", ",".join(map(str, srcs)), "--new", str(target),
             "--only", ",".join(map(str, tags))])
        cur = str(out)
        print(f"   fonts {srcs} -> slot {target}: {len(tags)} tags")
    print(f"translated tags: {len(translated)}")

    # --- per-face charsets --------------------------------------------------
    ascii_chars = set(chr(c) for c in range(0x20, 0x7F))
    as3_chars: set[str] = set()
    for p in (ROOT / "patch" / "as3").glob("*.as"):
        as3_chars |= {ch for ch in p.read_text(encoding="utf-8") if ord(ch) > 0x7E}
    from pipeline.ui.menu_labels import MENU_LABELS
    menu_chars = set("".join(text for text, _c, _o in MENU_LABELS.values()))

    slot_chars: dict[int, set[str]] = {s: set() for s in G1_REPLACED}
    for cid in translated:
        s = slot_of(cid)
        if s is not None:
            slot_chars[s] |= set("".join(UI_TRANSLATIONS[str(cid)]))
    # Untranslated tags that live on a replaced slot are re-imported verbatim,
    # so their characters must survive in that face too.
    for cid, (_is_edit, fonts) in tagfonts.items():
        if cid in translated:
            continue
        for f in fonts:
            if f in G1_REPLACED and cid in orig_texts:
                slot_chars[f] |= set(orig_texts[cid].read_text(encoding="utf-8"))
    charsets: dict[int, set[str]] = {}
    for slot in G1_REPLACED:
        cs = slot_chars[slot] | ascii_chars
        if slot in (92, 22, 94, 1106):   # faces that host runtime TextFields
            cs |= as3_chars
        if slot == 92:
            cs |= menu_chars
        charsets[slot] = cs - {"\n", "\r"}

    face_ttf: dict[int, Path] = {}
    for slot in sorted(G1_REPLACED):
        dst = ROOT / "work" / "fonts" / G1_SLOT_SUBSET[slot]
        subset(face_source_ttf(G1_SLOT_FACE[slot]), dst, charsets[slot])
        face_ttf[slot] = dst
        print(f"   slot {slot} <- {G1_SLOT_FACE[slot]} ({len(charsets[slot])} chars)")

    # --- replace the slots and re-import every tag that lands on them -------
    slot_users: set[int] = set()
    for slot in G1_REPLACED:
        slot_users |= texts_using_font(args.orig, slot)
    import_ids = sorted(translated | {c for c in slot_users if c in work_texts})
    static_ids = [c for c in import_ids if not tagfonts.get(c, (False, set()))[0]]
    edit_ids = [c for c in import_ids if tagfonts.get(c, (False, set()))[0]]
    print(f"text tags to import: {len(import_ids)} "
          f"({len(static_ids)} static, {len(edit_ids)} edit)")

    # FFDec keeps a repurposed font's style flags and bakes them into the CJK
    # outlines; clear them so each face is embedded exactly as drawn.
    unstyled = ROOT / "work" / "build_unstyled.swf"
    clear_font_style(cur, str(unstyled), {s: (True, True) for s in G1_REPLACED})
    cur = str(unstyled)

    # Empty the static tags before the font swap (FFDec's font import otherwise
    # remaps their stale glyph indices and overflows on unmapped glyphs), then
    # rebuild them from formatted text so each record/line survives.
    truncated = ROOT / "work" / "build_trunc.swf"
    print(f"emptied {truncate_static_texts(cur, str(truncated), set(static_ids))} "
          f"static tags before the font swap")
    cur = str(truncated)
    dumps = export_formatted(cur, static_ids) if static_ids else {}

    def tag_slot(cid: int) -> int:
        for f in tagfonts.get(cid, (False, set()))[1]:
            if f in G1_FONT_MAP:
                return G1_FONT_MAP[f]
        return 92

    def records_for(cid: int) -> list[str]:
        if str(cid) in UI_TRANSLATIONS:
            return [s for s in (x.strip("\r\n") for x in UI_TRANSLATIONS[str(cid)]) if s]
        raw = work_texts[cid].read_text(encoding="utf-8")
        return [s.strip() for s in raw.split(RECORDSEP) if s.strip()]

    fmt_dir = ROOT / "work" / "fmt_import"
    fmt_dir.mkdir(parents=True, exist_ok=True)
    repl = ["-replace", str(cur), str(tmp_ui)]
    for slot in sorted(G1_REPLACED):
        repl += [str(slot), str(face_ttf[slot])]
    for cid in edit_ids:
        # A DefineEditText stores a string, not glyph indices; the separator
        # collapses into a real newline.
        if str(cid) in UI_TRANSLATIONS:
            text = "\n".join(x for x in UI_TRANSLATIONS[str(cid)] if x)
        else:
            text = work_texts[cid].read_text(encoding="utf-8")
            text = text.replace("\r\n", "\n").replace("\r", "\n")
            text = text.replace("\n" + RECORDSEP + "\n", "\n").replace(RECORDSEP, "\n")
        p = fmt_dir / f"{cid}.txt"
        p.write_text(text, encoding="utf-8")
        repl += [str(cid), str(p)]
    fallback = 0
    for cid in static_ids:
        segs = records_for(cid)
        famt = formatted_import(dumps.get(cid, ""), segs, tag_slot(cid))
        if famt is None:
            fallback += 1
            famt = ("\n" + RECORDSEP + "\n").join(segs)
        p = fmt_dir / f"{cid}.txt"
        p.write_text(famt, encoding="utf-8")
        repl += [str(cid), str(p)]
    if fallback:
        print(f"   {fallback} static tags fell back to plain import")
    run(["java", "-Xmx4g", "-jar", str(FFDEC), *repl])

    # Second, formatted import for the tags whose plain import kept the original
    # kerning (garbled indices or baked uneven letterspacing).  See
    # make_formatted_text.
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
        cur_fonts = text_tag_fonts(str(tmp_ui))

        def fix_slot(cid: int) -> int:
            for f in cur_fonts.get(cid, (False, set()))[1]:
                if f in G1_REPLACED:
                    return f
            return 92

        fix = ["-replace", str(tmp_ui), str(fixed)]
        for cid in fix_ids:
            text = make_formatted_text(dumps.get(cid, ""),
                                       UI_TRANSLATIONS[str(cid)], fix_slot(cid))
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
        "uv", "run", "python", str(ROOT / "pipeline" / "ui" / "menu_labels.py"),
        "--swf", str(tmp_sub), "--out", str(tmp_menu), "--orig", args.orig,
    ])
    run([
        "uv", "run", "python", str(ROOT / "pipeline" / "lib" / "align_controls.py"),
        "--swf", str(tmp_menu), "--out", str(out), "--orig", args.orig,
    ])
    size = compress_swf(str(out))
    print(f"built {out} ({size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

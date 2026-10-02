"""Build the ROTD2 UI localisation (baked DefineText + CJK font slots).

ROTD1 shipped two UI faces, so its build maps them onto two CJK slots.  ROTD2
ships *twelve* real embedded faces, each with its own visual role, so the
Chinese is adapted per face instead of collapsing every body font into one
serif slot:

    original face            CJK face
    Dirty Ego        93      RoadOfTheDeadCN     (hand-drawn display)
    DESTRUCCION   10419      RoadOfTheDeadCN     (grunge display)
    DS-Digital    10315      RoadOfTheDeadCN     (decorative numerals)
    Arial Black       1      Noto Sans SC Black  (heavy sans)
    Arial             95      Noto Sans SC        (body sans)
    Verdana         134      Noto Sans SC
    Arial Bold     3066      Noto Sans SC Bold
    Arial Bold    10082      Noto Sans SC Bold
    Euromode Bold  8705      Noto Sans SC Bold
    Arial Italic      3      Noto Sans SC (*)
    Arial Bold Italic 132    Noto Sans SC Bold (*)
    Typenoksidi    3099      Noto Serif SC       (book body)

    (*) the italic slots keep their italic flag, so FFDec renders the CJK face
        oblique exactly like the Latin italic it replaces.

Only *translated* tags are repointed, so the original Dirty Ego face (logo,
HUD numerals, credits) stays byte-identical.  Every tag that lives on a
repurposed slot must be re-imported, otherwise its stale glyph indices decode
through the CJK face as garbage.

Translation data is read through ``pipeline/translations.py`` from
``ROT_TRANSLATIONS`` (defaults to ``data/paratranz2``).
"""
from __future__ import annotations

import argparse
import os
import struct
import subprocess
import sys
import zlib
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("ROT_TRANSLATIONS", str(ROOT / "data" / "paratranz2"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_all import (  # noqa: E402
    export_plain_texts,
    make_formatted_text,
    text_tag_fonts,
    texts_using_font,
)
from align_controls import build_formatted, export_formatted, parse_formatted  # noqa: E402
from remap_font import clear_font_style  # noqa: E402
from translations import AS3, UI_TRANSLATIONS, load as load_translations  # noqa: E402

FFDEC = ROOT / "tools" / "ffdec" / "ffdec-cli.jar"
SEP = "--- RECORDSEPARATOR ---"

# --- font adaptation map ---------------------------------------------------
# ROTD2 has no free font slot, so low-use originals are repurposed.  ``8705``
# (Euromode Bold, a single edit text) hosts the hand-drawn display face that
# all the translated Dirty Ego / DESTRUCCION / DS-Digital text uses.
DISPLAY_SLOT = 8705

# original font id -> slot that carries the matching CJK face
FONT_MAP: dict[int, int] = {
    93: DISPLAY_SLOT,     # Dirty Ego
    10419: DISPLAY_SLOT,  # DESTRUCCION
    10315: DISPLAY_SLOT,  # DS-Digital
    1: 1,                 # Arial Black -> sans black
    3: 3,                 # Arial Italic -> sans italic
    95: 95,               # Arial -> sans
    134: 95,              # Verdana -> sans
    3066: 3066,           # Arial Bold -> sans bold
    10082: 3066,          # Arial Bold -> sans bold
    8705: 3066,           # Euromode Bold -> sans bold
    132: 132,             # Arial Bold Italic -> sans bold italic
    3099: 3099,           # Typenoksidi -> serif
}

# Slots whose DefineFont is replaced with a (subset) CJK face.
REPLACED_SLOTS: set[int] = {DISPLAY_SLOT, 1, 3, 95, 3066, 132, 3099}

SLOT_FACE: dict[int, str] = {
    DISPLAY_SLOT: "display",
    1: "sans_black",
    3: "sans_italic",
    95: "sans",
    3066: "sans_bold",
    132: "sans_bold_italic",
    3099: "serif",
}
# slot -> (clear bold?, clear italic?) before the font import.  Italic slots
# keep the italic bit so FFDec still renders the CJK face slanted.
SLOT_CLEAR: dict[int, tuple[bool, bool]] = {
    DISPLAY_SLOT: (True, True),
    1: (True, True),
    3: (True, False),
    95: (True, True),
    3066: (True, True),
    132: (True, False),
    3099: (True, True),
}

SRC_DISPLAY = ROOT / "data" / "fonts" / "RoadOfTheDeadCN.ttf"
SRC_SERIF = ROOT / "data" / "fonts" / "NotoSerifSC-SemiBold.ttf"
SRC_SANS_VF = ROOT / "data" / "fonts" / "NotoSansSC-VF.ttf"

# face -> source: ("ttf", path) or ("wght", weight of the Noto Sans SC VF)
FACE_SOURCE: dict[str, tuple[str, object]] = {
    "display": ("ttf", SRC_DISPLAY),
    "serif": ("ttf", SRC_SERIF),
    "sans": ("wght", 400),
    "sans_italic": ("wght", 400),
    "sans_bold": ("wght", 700),
    "sans_bold_italic": ("wght", 700),
    "sans_black": ("wght", 900),
}
# face -> subset file name; faces sharing outlines share one subset
FACE_SUBSET: dict[str, str] = {
    "display": "ui_display.ttf",
    "serif": "ui_serif.ttf",
    "sans": "ui_sans.ttf",
    "sans_italic": "ui_sans.ttf",
    "sans_bold": "ui_sans_bold.ttf",
    "sans_bold_italic": "ui_sans_bold.ttf",
    "sans_black": "ui_sans_black.ttf",
}


def run(args: list[str]) -> None:
    proc = subprocess.run(args, capture_output=True, text=True)
    if proc.returncode != 0:
        print("\n".join(proc.stdout.splitlines()[-15:]))
        print(proc.stderr[-3000:], file=sys.stderr)
        raise SystemExit(f"command failed ({proc.returncode}): {' '.join(args[:4])}...")
    for ln in [x for x in proc.stdout.splitlines() if x.strip()][-2:]:
        print("   ", ln)


SRC_SCRIPTS = ROOT / "work2" / "scripts" / "scripts"


def ui_segments(cid: int) -> list[str]:
    """A tag's translated records, only truly empty lines removed.

    Blank lines in ``ui.csv`` separate records, but a record may legitimately be
    a single space (the original tags use whitespace records as spacers between
    the small and large location lines).  Dropping those with ``.strip()``
    collapsed the record count and left the extra original record in place, so
    the tag imported garbage.  Only empty strings are separators.
    """
    segs = [s.strip("\r\n") for s in UI_TRANSLATIONS[str(cid)]]
    return [s for s in segs if s]


def formatted_import(dump: str, segs: list[str], slot: int) -> str | None:
    """Rebuild a truncated static tag's formatted text with translated records.

    ``make_formatted_text`` in ``build_all`` early-outs when the dump has no
    spacing pairs (the fix pass only re-imports squeezed tags); the initial
    import needs the same record-by-record rebuild unconditionally.
    """
    if not dump or not segs:
        return None
    tag, pre, records = parse_formatted(dump)
    if len(records) != len(segs):
        return None
    new_records: list[tuple[str, str]] = []
    for (hdr, _old), text in zip(records, segs):
        keep = [ln for ln in hdr.splitlines()
                if not ln.strip().startswith(("spacing", "letterspacing", "font"))]
        h = "\n".join(keep)
        if not h.endswith("\n"):
            h += "\n"
        h += f"font {slot}\n"
        new_records.append((h, text.strip("\r\n")))
    return build_formatted(tag, pre, new_records)


def apply_layout_patch(s: str) -> str:
    """Hide the dead Newgrounds preloader ad and centre the loading panels.

    ROTD2's preloader shows the game key art / house ad from the Newgrounds
    FlashAd component on one side and the story/login panel on the other.  The
    ad service is long dead, so the ad slot is blank.  We hide the ad
    (``NGAds``/``NGPromo``) and recentre whichever panel is visible
    (``PreloaderStory`` or ``PassportPanel``) on the stage.
    """
    s = s.replace("this.NGPromo.visible = this.bHasPromo;",
                  "this.NGPromo.visible = false;")
    s = s.replace("this.NGAds.visible = !this.bHasPromo;",
                  "this.NGAds.visible = false;")
    s = s.replace(
        "addEventListener(Event.ENTER_FRAME,this.EnterFrameHandler);",
        "addEventListener(Event.ENTER_FRAME,this.EnterFrameHandler);\n      this.CenterPreloaderContent();",
    )
    s = s.replace("Mouse.show();",
                  "Mouse.show();\n         this.CenterPreloaderContent();")
    # These panels are toggled visible later (TestSession / session callbacks), so
    # re-centre whenever one is shown.
    s = s.replace("this.PassportPanel.visible = true;",
                  "this.PassportPanel.visible = true;\n      this.CenterPreloaderContent();")
    s = s.replace("this.PreloaderStory.visible = true;",
                  "this.PreloaderStory.visible = true;\n      this.CenterPreloaderContent();")

    method = (
        "   public function CenterPreloaderContent() : *\n"
        "   {\n"
        "      if(this.stage == null)\n"
        "      {\n"
        "         return;\n"
        "      }\n"
        "      var cx:Number = this.stage.stageWidth / 2;\n"
        "      if(this.PreloaderStory != null && this.PreloaderStory.visible)\n"
        "      {\n"
        "         var b1:Rectangle = this.PreloaderStory.getBounds(this);\n"
        "         this.PreloaderStory.x = Math.round(this.PreloaderStory.x + (cx - (b1.x + b1.width / 2)));\n"
        "      }\n"
        "      if(this.PassportPanel != null && this.PassportPanel.visible)\n"
        "      {\n"
        "         var b2:Rectangle = this.PassportPanel.getBounds(this);\n"
        "         this.PassportPanel.x = Math.round(this.PassportPanel.x + (cx - (b2.x + b2.width / 2)));\n"
        "      }\n"
        "   }\n   \n"
    )
    s = s.replace("   internal function __setProp_NGAds_Scene1_Content_0",
                  method + "   internal function __setProp_NGAds_Scene1_Content_0", 1)
    if "CenterPreloaderContent() : *" not in s:
        raise SystemExit("failed to inject CenterPreloaderContent into MainTimeline.as")
    return s


def as3_script_patches() -> dict[str, str]:
    """Apply the translated AS3 string literals (``as3.csv``) to the sources."""
    from translations import AS3

    dst = ROOT / "work2" / "patch" / "as3"
    dst.mkdir(parents=True, exist_ok=True)
    patches: dict[str, str] = {}
    for ctx, mapping in AS3.items():
        src = SRC_SCRIPTS / ctx.replace("\\", "/")
        if not src.exists():
            continue
        txt = src.read_text(encoding="utf-8")
        applied = 0
        for old, new in mapping.items():
            w_old, w_new = f'"{old}"', f'"{new}"'
            if w_old in txt:
                txt = txt.replace(w_old, w_new)
                applied += 1
            elif old.startswith('"') and old.endswith('"') and old in txt:
                txt = txt.replace(old, new)
                applied += 1
        if not applied:
            continue
        name = ctx.replace("\\", "/")[:-3].replace("/", ".")
        p = dst / f"{name}.as"
        p.write_text(txt, encoding="utf-8")
        patches[name] = str(p)
        print(f"   as3 {ctx}: {applied}/{len(mapping)}")
    return patches


def build_script_patches() -> list[tuple[str, str]]:
    """Every AS3 script to re-import: literal translations + subtitles + layout."""
    import make_dtsound

    patches = as3_script_patches()

    patches["DTSound"] = str(make_dtsound.generate(
        original=SRC_SCRIPTS / "DTSound.as",
        out=ROOT / "work2" / "patch" / "DTSound.as",
        durations=ROOT / "work2" / "asr_gpu.json",
        stream_timing=ROOT / "work2" / "stream_timing.json",
        swf=ROOT / "dist" / "Road-Of-The-Dead2.swf",
        min_split_secs=7.5,
        debug=False,
        # ROTD2's root audio stream starts at timeline frame 75 at 30 fps, and
        # the stream sound lags the timeline by ~3.1s (measured against the
        # decoded MP3 packet times), so t = (frame-1)/30 - (74+93)/30.
        stream_offset=(74.0 + 93.0) / 30.0,
    ))

    bg_text = Path(patches.get("BasicGame", SRC_SCRIPTS / "BasicGame.as")).read_text(
        encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    anchor = ("         this.m_Viewport = new Viewport(this.m_RootMC.stage.stageWidth,"
              "this.m_RootMC.stage.stageHeight);\n")
    if "DTSound.InitSubtitles();" not in bg_text:
        if anchor not in bg_text:
            raise SystemExit("BasicGame.Init() anchor not found for subtitle hook")
        bg_text = bg_text.replace(anchor, anchor + "         DTSound.InitSubtitles();\n", 1)
    bg = ROOT / "work2" / "patch" / "BasicGame.as"
    bg.write_text(bg_text, encoding="utf-8")
    patches["BasicGame"] = str(bg)

    mt_name = "RoadOfTheDead_fla.MainTimeline"
    mt_text = Path(patches.get(
        mt_name, SRC_SCRIPTS / "RoadOfTheDead_fla" / "MainTimeline.as")).read_text(
        encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    mt = ROOT / "work2" / "patch" / "MainTimeline.as"
    mt.write_text(apply_layout_patch(mt_text), encoding="utf-8")
    patches[mt_name] = str(mt)

    return list(patches.items())


def sans_weight(weight: int) -> Path:
    """Static instance of the Noto Sans SC variable font at ``weight``."""
    out = ROOT / "work2" / "fonts" / f"NotoSansSC-{weight}.ttf"
    out.parent.mkdir(parents=True, exist_ok=True)
    if not SRC_SANS_VF.exists():
        raise SystemExit(
            f"missing {SRC_SANS_VF} -- run: pwsh -File pipeline/fetch-fonts.ps1")
    if not out.exists() or out.stat().st_mtime < SRC_SANS_VF.stat().st_mtime:
        from fontTools.ttLib import TTFont
        from fontTools.varLib import instancer
        f = TTFont(SRC_SANS_VF)
        instancer.instantiateVariableFont(
            f, {"wght": weight}, inplace=True, updateFontNames=True)
        f.save(out)
    return out


def truncate_static_texts(infile: str, outfile: str, ids: set[int]) -> int:
    """Reduce each given static DefineText tag to empty records.

    FFDec's font import remaps every existing text tag's glyphs onto the new
    face by character.  A face whose glyphs have no Unicode mapping (Dirty Ego
    has several) makes FFDec assign indices past the new font's table, which
    then overflows ``glyphToChar`` and aborts the whole import.  Emptying the
    tags first leaves nothing to remap; their record count and style are kept so
    the formatted import can rebuild each line in place.
    """
    from remap_font import load_swf_raw, write_swf_fws

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


def _empty_records(body: bytes, code: int) -> bytes | None:
    """Keep every record's style (font/x/y/height) but drop all its glyphs."""
    from remap_font import Bits

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


def face_source(face: str) -> Path:
    kind, val = FACE_SOURCE[face]
    return sans_weight(int(val)) if kind == "wght" else Path(val)  # type: ignore[arg-type]


def build_subsets(charsets: dict[str, set[str]]) -> dict[str, Path]:
    """Subset each distinct face to the glyphs only *its* slots draw.

    Every face embedding the same full charset costs megabytes of glyph data,
    so each face gets the union of the characters used by the tags that land on
    its slots (plus ASCII and the AS3 runtime strings, which can target any
    slot's TextField).  Faces sharing outlines share one subset file.
    """
    outdir = ROOT / "work2" / "fonts"
    outdir.mkdir(parents=True, exist_ok=True)
    raw: dict[str, Path] = {}
    for face, name in FACE_SUBSET.items():
        if name in raw:
            continue
        dst = outdir / name
        charset = outdir / f"{name}.charset.txt"
        charset.write_text("".join(sorted(charsets[name])), encoding="utf-8")
        run(["uv", "run", "pyftsubset", str(face_source(face)),
             f"--text-file={charset}", f"--output-file={dst}",
             "--no-hinting", "--desubroutinize",
             "--drop-tables+=DSIG,GSUB,GPOS,GDEF,BASE,STAT,gasp,vhea,vmtx"])
        raw[name] = dst
    return {face: raw[name] for face, name in FACE_SUBSET.items()}


def compress_swf(path: str, level: int = 9) -> int:
    """Rewrite an uncompressed (FWS) SWF as zlib-compressed (CWS).

    The header keeps the original uncompressed length; only the body is
    compressed, matching how the shipped game SWF is stored.
    """
    data = Path(path).read_bytes()
    if data[:3] == b"CWS":
        return len(data)
    if data[:3] != b"FWS":
        raise SystemExit(f"{path}: not an FWS uncompressed SWF")
    body = zlib.compress(data[8:], level)
    out = b"CWS" + data[3:4] + len(data).to_bytes(4, "little") + body
    Path(path).write_bytes(out)
    return len(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--orig", default=str(ROOT / "dist" / "Road-Of-The-Dead2.swf"))
    ap.add_argument("--texts", default=str(ROOT / "work2" / "scripts" / "texts"))
    ap.add_argument("--out", default=str(ROOT / "dist" / "rotd2-zh-ui.swf"))
    args = ap.parse_args()

    texts = {int(p.stem): p for p in Path(args.texts).glob("*.txt")}
    # The game title keeps its original face and English wording (ROTD2 standard):
    # leave those tags completely alone so they are not repointed or re-imported.
    title_ids = set()
    for key, row in load_translations("ui").items():
        if key.startswith("ui_"):
            flat = "".join(row["original"].split()).lower()
            if flat in ("roadofthedead", "roadofthedead2"):
                title_ids.add(int(key[3:]))
    translated = {int(k) for k in UI_TRANSLATIONS if int(k) in texts} - title_ids
    if title_ids:
        print(f"game title kept as-is: {sorted(title_ids)}")
    tagfonts = text_tag_fonts(args.orig)

    # Which tags use each original face (for building the per-face remap sets).
    font_tags: dict[int, list[tuple[int, bool]]] = defaultdict(list)
    for cid, (is_edit, fonts) in tagfonts.items():
        for f in fonts:
            font_tags[f].append((cid, is_edit))

    print(f"translated tags: {len(translated)}")

    # --- repoint translated tags (and runtime TextFields) to the CJK slots ---
    # A DefineEditText may be assigned Chinese at runtime even when its baked
    # text is untranslated, so every edit text of a mapped face moves too.
    remap_steps: list[tuple[int, int, list[int]]] = []
    for f, target in FONT_MAP.items():
        if target == f:
            continue
        tags = sorted({cid for cid, is_edit in font_tags.get(f, [])
                       if (cid in translated or is_edit)
                       and cid not in title_ids and cid in texts})
        if tags:
            remap_steps.append((f, target, tags))
    # Process sources that are themselves repurposed slots first, so a tag that
    # mixes faces does not get its freshly-written target slot overwritten.
    remap_steps.sort(key=lambda s: (s[0] not in REPLACED_SLOTS,))
    remap = ROOT / "pipeline" / "remap_font.py"
    cur = args.orig
    for f, target, tags in remap_steps:
        out = ROOT / "work2" / f"ui_remap_{f}_to_{target}.swf"
        run(["uv", "run", "python", str(remap), str(cur), str(out),
             "--old", str(f), "--new", str(target),
             "--only", ",".join(map(str, tags))])
        cur = str(out)
        print(f"   font {f} -> slot {target}: {len(tags)} tags")

    # Slots 1/3/95/132/3066/3099/8705 are repurposed from styled originals.
    # Clear the style bits FFDec would otherwise bake into the CJK outlines,
    # except on the italic slots (3, 132), whose italic bit gives the slant.
    spec = {slot: SLOT_CLEAR[slot] for slot in sorted(REPLACED_SLOTS)}
    unstyled = ROOT / "work2" / "ui_unstyled.swf"
    touched = clear_font_style(cur, str(unstyled), spec)
    if touched:
        print("font style flags -> " + ", ".join(
            f"{fid}:{old:#04x}->{new:#04x}" for fid, (old, new) in sorted(touched.items())))
        cur = str(unstyled)

    # Replace every repurposed slot and re-import every tag that ends up on one
    # of them (translated or not), so no stale glyph index survives.
    slot_users: set[int] = set()
    for slot in REPLACED_SLOTS:
        slot_users |= texts_using_font(args.orig, slot)
    import_ids = sorted((translated | {c for c in slot_users if c in texts}) - title_ids)
    static_ids = [c for c in import_ids if not tagfonts.get(c, (False, set()))[0]]
    edit_ids = [c for c in import_ids if tagfonts.get(c, (False, set()))[0]]
    print(f"re-importing {len(import_ids)} tags on replaced slots "
          f"({len(static_ids)} static, {len(edit_ids)} edit)")

    def tag_slot(cid: int) -> int:
        for f in tagfonts.get(cid, (False, set()))[1]:
            if f in FONT_MAP:
                return FONT_MAP[f]
        return DISPLAY_SLOT

    # Each face only needs the glyphs drawn by the tags that land on its slots,
    # plus ASCII and the AS3 runtime strings (which any slot's TextField may
    # show).  Embedding the whole charset in all seven faces is what made the
    # SWF balloon; per-face subsets cut the glyph data substantially.
    ascii_chars = set(chr(c) for c in range(0x20, 0x7F))
    as3_chars: set[str] = set()
    for mapping in AS3.values():
        for tr in mapping.values():
            as3_chars |= set(tr)
    as3_chars -= {"\n", "\r"}
    slot_chars: dict[int, set[str]] = {slot: set() for slot in REPLACED_SLOTS}
    for cid in import_ids:
        if str(cid) in UI_TRANSLATIONS:
            slot_chars[tag_slot(cid)] |= set("".join(UI_TRANSLATIONS[str(cid)]))
        else:
            slot_chars[tag_slot(cid)] |= set(texts[cid].read_text(encoding="utf-8"))
    charsets: dict[str, set[str]] = {}
    for slot in REPLACED_SLOTS:
        name = FACE_SUBSET[SLOT_FACE[slot]]
        charsets.setdefault(name, set()).update(slot_chars[slot] | ascii_chars | as3_chars)
    for cs in charsets.values():
        cs -= {"\n", "\r"}
    faces = build_subsets(charsets)
    for slot in sorted(REPLACED_SLOTS):
        print(f"   slot {slot} <- {SLOT_FACE[slot]} "
              f"({faces[SLOT_FACE[slot]].name}, "
              f"{len(charsets[FACE_SUBSET[SLOT_FACE[slot]]])} chars)")

    # Empty the static tags before the font swap (see truncate_static_texts),
    # then rebuild them from formatted text so each record/line survives.
    truncated = ROOT / "work2" / "ui_truncated.swf"
    print(f"emptied {truncate_static_texts(cur, str(truncated), set(static_ids))} "
          f"static tags before the font swap")
    cur = str(truncated)
    dumps = export_formatted(cur, static_ids) if static_ids else {}

    def records_for(cid: int) -> list[str]:
        if str(cid) in UI_TRANSLATIONS:
            return ui_segments(cid)
        raw = texts[cid].read_text(encoding="utf-8")
        return [s.strip() for s in raw.split(SEP) if s.strip()]

    outdir = ROOT / "work2" / "ui_texts"
    outdir.mkdir(parents=True, exist_ok=True)
    repl: list[str] = []
    for slot in sorted(REPLACED_SLOTS):
        repl += [str(slot), str(faces[SLOT_FACE[slot]])]
    for cid in edit_ids:
        # A DefineEditText stores a string, not glyph indices, so it imports as
        # plain text with real newlines.
        if str(cid) in UI_TRANSLATIONS:
            text = "\n".join(ui_segments(cid))
        else:
            text = texts[cid].read_text(encoding="utf-8")
            text = text.replace("\r\n", "\n").replace("\r", "\n")
            text = text.replace("\n" + SEP + "\n", "\n").replace(SEP, "\n")
        p = outdir / f"{cid}.txt"
        p.write_text(text, encoding="utf-8")
        repl += [str(cid), str(p)]
    fallback = 0
    for cid in static_ids:
        segs = records_for(cid)
        famt = formatted_import(dumps.get(cid, ""), segs, tag_slot(cid))
        if famt is None:
            fallback += 1
            famt = ("\n" + SEP + "\n").join(segs)
        p = outdir / f"{cid}.txt"
        p.write_text(famt, encoding="utf-8")
        repl += [str(cid), str(p)]
    if fallback:
        print(f"   {fallback} static tags fell back to plain import")
    for name, path in build_script_patches():
        repl += [name, path]
    # 900+ pairs overflow the Windows command line, so pass them via an argsfile.
    argsfile = ROOT / "work2" / "ui_replace_args.txt"
    argsfile.write_text("\n".join(repl), encoding="utf-8")
    run(["java", "-Xmx4g", "-jar", str(FFDEC), "-replace",
         cur, str(args.out), str(argsfile)])

    # FFDec's plain-text import round-trips the tag's original (Latin) kerning as
    # per-record ``letterspacing``/``spacingpair`` entries.  Those pairs no longer
    # describe the CJK glyphs, so they visibly squeeze the translated text on top
    # of itself, and a pair that cannot round-trip (an empty/quote key) aborts and
    # leaves the old glyph indices in place (garbage).  Detect both from a
    # formatted dump of the imported tags and re-import them with every spacing
    # entry dropped and the font forced to the tag's own CJK slot -- the same
    # second pass the ROTD1 build uses.
    cur = str(args.out)
    cur_fonts = text_tag_fonts(cur)

    def slot_for(cid: int) -> int:
        for f in cur_fonts.get(cid, (False, set()))[1]:
            if f in REPLACED_SLOTS:
                return f
        return DISPLAY_SLOT

    got = export_plain_texts(cur)
    failed = [cid for cid in sorted(translated)
              if ui_segments(cid) != got.get(cid, [])]
    dumps = export_formatted(cur, sorted(translated))
    spaced = [cid for cid in sorted(translated)
              if cid not in failed
              and ("spacing" in dumps.get(cid, "")
                   or "letterspacing" in dumps.get(cid, ""))]
    fix_ids = sorted(set(failed) | set(spaced))
    if fix_ids:
        print(f"re-importing {len(fix_ids)} kerning tags "
              f"(garbled={len(failed)}, squeezed={len(spaced)})")
        fmtdir = ROOT / "work2" / "fmt_texts"
        fmtdir.mkdir(parents=True, exist_ok=True)
        fixed = ROOT / "work2" / "ui_fixed.swf"
        fix = ["-replace", cur, str(fixed)]
        for cid in fix_ids:
            text = make_formatted_text(dumps.get(cid, ""), ui_segments(cid),
                                       slot_for(cid))
            if text is not None:
                p = fmtdir / f"{cid}.txt"
                p.write_text(text, encoding="utf-8")
                fix += [str(cid), str(p)]
        if len(fix) > 3:
            run(["java", "-Xmx4g", "-jar", str(FFDEC), *fix])
            cur = str(fixed)

    # Rescale the main-menu captions so the Chinese ink height matches the English
    # it replaces (the CJK face at the Latin em is ~1.5x too tall, which flattens
    # the menu hierarchy and pushes the longest caption off the stage).  Must run
    # before the alignment pass, which measures the post-scale renders.
    fitted = ROOT / "work2" / "menu_fit.swf"
    run(["uv", "run", "python", str(ROOT / "pipeline" / "fit_menu_rotd2.py"),
         "--swf", cur, "--orig", str(args.orig), "--out", str(fitted)])
    if fitted.exists():
        cur = str(fitted)

    # Re-centre labels the original centred: FFDec lays the Chinese out from each
    # English line's left origin, so single labels drift and multi-line blocks come
    # out ragged/clipped.  Static DefineText only -- dynamic fields align themselves.
    align_ids = sorted(cid for cid in translated
                       if not tagfonts.get(cid, (False, set()))[0])
    aligned = Path(str(args.out) + ".aligned.swf")
    run(["uv", "run", "python", str(ROOT / "pipeline" / "align_rotd2.py"),
         "--swf", cur, "--orig", str(args.orig),
         "--out", str(aligned), "--ids", ",".join(map(str, align_ids)),
         "--outdir", str(ROOT / "work2" / "aligned")])
    if aligned.exists():
        Path(args.out).unlink()
        aligned.rename(args.out)

    # The Survival Guide book caption is vector art, not text; redraw it last.
    booked = Path(str(args.out) + ".book.swf")
    run(["uv", "run", "python", str(ROOT / "pipeline" / "book_labels_rotd2.py"),
         "--swf", str(args.out), "--orig", str(args.orig), "--out", str(booked)])
    if booked.exists():
        Path(args.out).unlink()
        booked.rename(args.out)

    # Every step above rewrites the SWF uncompressed (FWS), while the original
    # ships zlib-compressed (CWS).  Re-compressing the finished file is the
    # single biggest size win -- the CJK glyph data and text shrink ~13%.
    compressed = compress_swf(str(args.out))
    print(f"built {args.out} ({compressed} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

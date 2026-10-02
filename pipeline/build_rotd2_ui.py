"""Build the ROTD2 UI localisation (baked DefineText + CJK font slots).

ROTD2 has no free font slot, so two low-use, layout-capable fonts are
repurposed as the CJK slots:

    display (Dirty Ego  93) -> slot 132 (was Arial Bold Italic)
    body    (Arial      95) -> slot 8705 (was Euromode Bold)

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
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("ROT_TRANSLATIONS", str(ROOT / "data" / "paratranz2"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_all import text_tag_fonts, texts_using_font  # noqa: E402
from translations import AS3, UI_TRANSLATIONS, load as load_translations  # noqa: E402

FFDEC = ROOT / "tools" / "ffdec" / "ffdec-cli.jar"
SEP = "--- RECORDSEPARATOR ---"
DISPLAY_OLD = 93
BODY_OLD = {1, 3, 95, 132, 134, 3066, 3099, 10419}
# Fonts used by DefineEditText (runtime text fields); they must be repointed to a
# CJK face as well or Chinese set at runtime renders blank (no glyphs).
EDIT_FONTS = {1, 3, 93, 95, 132, 134, 3066, 3099, 8705}


def run(args: list[str]) -> None:
    proc = subprocess.run(args, capture_output=True, text=True)
    if proc.returncode != 0:
        print("\n".join(proc.stdout.splitlines()[-15:]))
        print(proc.stderr[-3000:], file=sys.stderr)
        raise SystemExit(f"command failed ({proc.returncode}): {' '.join(args[:4])}...")
    for ln in [x for x in proc.stdout.splitlines() if x.strip()][-2:]:
        print("   ", ln)


SRC_SCRIPTS = ROOT / "work2" / "scripts" / "scripts"


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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--orig", default=str(ROOT / "dist" / "Road-Of-The-Dead2.swf"))
    ap.add_argument("--texts", default=str(ROOT / "work2" / "scripts" / "texts"))
    ap.add_argument("--out", default=str(ROOT / "dist" / "rotd2-zh-ui.swf"))
    ap.add_argument("--display-font-id", type=int, default=132)
    ap.add_argument("--body-font-id", type=int, default=8705)
    ap.add_argument("--display-font", default=str(ROOT / "work2" / "fonts" / "ui_cjk.ttf"))
    ap.add_argument("--body-font", default=str(ROOT / "work2" / "fonts" / "ui_body.ttf"))
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

    display_ids, body_ids = [], []
    for cid in sorted(translated):
        fonts = tagfonts.get(cid, (False, set()))[1]
        if fonts & {DISPLAY_OLD}:
            display_ids.append(cid)
        elif fonts & BODY_OLD or cid in (8706,):
            body_ids.append(cid)
    print(f"translated tags: {len(translated)}  display={len(display_ids)} body={len(body_ids)}")

    # Repoint translated tags to the two CJK slots.
    remap = ROOT / "pipeline" / "remap_font.py"
    base1 = ROOT / "work2" / "ui_base1.swf"
    base = ROOT / "work2" / "ui_base.swf"
    run(["uv", "run", "python", str(remap), args.orig, str(base1),
         "--old", str(DISPLAY_OLD), "--new", str(args.display_font_id),
         "--only", ",".join(map(str, display_ids))])
    run(["uv", "run", "python", str(remap), str(base1), str(base),
         "--old", ",".join(map(str, sorted(BODY_OLD))), "--new", str(args.body_font_id),
         "--only", ",".join(map(str, body_ids))])

    # Runtime TextFields (DefineEditText) draw strings set by AS3; repoint those
    # to the CJK body face too, otherwise Chinese renders blank on screens like
    # the character upgrade page.
    edit_ids = sorted(cid for cid, (is_edit, fonts) in tagfonts.items()
                      if is_edit and (fonts & EDIT_FONTS))
    base2 = ROOT / "work2" / "ui_base2.swf"
    if edit_ids:
        run(["uv", "run", "python", str(remap), str(base), str(base2),
             "--old", ",".join(map(str, sorted(EDIT_FONTS))),
             "--new", str(args.body_font_id),
             "--only", ",".join(map(str, edit_ids))])
        cur = str(base2)
    else:
        cur = str(base)

    # Charset = every translated glyph + ASCII.
    chars: set[str] = set(chr(c) for c in range(0x20, 0x7F))
    for cid in translated:
        for seg in UI_TRANSLATIONS[str(cid)]:
            chars |= set(seg)
    # Dynamic TextFields embed this face too, so include the AS3 strings.
    for mapping in AS3.values():
        for tr in mapping.values():
            chars |= set(tr)
    chars.discard("\n")
    chars.discard("\r")
    (ROOT / "work2" / "fonts").mkdir(parents=True, exist_ok=True)
    charset = ROOT / "work2" / "fonts" / "charset.txt"
    charset.write_text("".join(sorted(chars)), encoding="utf-8")

    run(["uv", "run", "pyftsubset", str(ROOT / "data" / "fonts" / "RoadOfTheDeadCN.ttf"),
         f"--text-file={charset}", f"--output-file={args.display_font}",
         "--no-hinting", "--desubroutinize", "--drop-tables+=DSIG"])
    run(["uv", "run", "pyftsubset", str(ROOT / "data" / "fonts" / "NotoSerifSC-SemiBold.ttf"),
         f"--text-file={charset}", f"--output-file={args.body_font}",
         "--no-hinting", "--desubroutinize", "--drop-tables+=DSIG"])

    # Replace the two slots and re-import every tag that ends up on one of them
    # (translated or not) -- otherwise its stale glyph indices decode through the
    # CJK face as garbage.  Untranslated slot users keep their original text.
    slot_users = (texts_using_font(args.orig, args.display_font_id)
                  | texts_using_font(args.orig, args.body_font_id))
    import_ids = sorted((translated | {c for c in slot_users if c in texts}) - title_ids)
    print(f"re-importing {len(import_ids)} tags on replaced slots")

    outdir = ROOT / "work2" / "ui_texts"
    outdir.mkdir(parents=True, exist_ok=True)
    repl = [str(args.display_font_id), args.display_font,
            str(args.body_font_id), args.body_font]
    for cid in import_ids:
        if str(cid) in UI_TRANSLATIONS:
            segs = [s.strip("\r\n") for s in UI_TRANSLATIONS[str(cid)]]
            segs = [s for s in segs if s.strip()]
            text = ("\n" + SEP + "\n").join(segs)
        else:
            text = texts[cid].read_text(encoding="utf-8")
        p = outdir / f"{cid}.txt"
        p.write_text(text, encoding="utf-8")
        repl += [str(cid), str(p)]
    for name, path in build_script_patches():
        repl += [name, path]
    # 900+ pairs overflow the Windows command line, so pass them via an argsfile.
    argsfile = ROOT / "work2" / "ui_replace_args.txt"
    argsfile.write_text("\n".join(repl), encoding="utf-8")
    run(["java", "-Xmx4g", "-jar", str(FFDEC), "-replace",
         cur, str(args.out), str(argsfile)])

    # Re-centre single-record labels the original centred: FFDec lays the shorter
    # Chinese out from the tag's left origin, so they come out off-axis otherwise.
    center_ids = sorted(int(k) for k in UI_TRANSLATIONS
                        if len(UI_TRANSLATIONS[k]) == 1 and int(k) in texts
                        and int(k) not in title_ids)
    aligned = Path(str(args.out) + ".aligned.swf")
    run(["uv", "run", "python", str(ROOT / "pipeline" / "align_rotd2.py"),
         "--swf", str(args.out), "--orig", str(args.orig),
         "--out", str(aligned), "--ids", ",".join(map(str, center_ids)),
         "--outdir", str(ROOT / "work2" / "aligned")])
    if aligned.exists():
        Path(args.out).unlink()
        aligned.rename(args.out)

    print(f"built {args.out} ({Path(args.out).stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

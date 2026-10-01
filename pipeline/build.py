"""Full pipeline: original SWF -> localised SWF.

Steps
  1. export scripts / texts / symbol classes with FFDec
  2. generate the subtitle-instrumented DTSound.as from data/subtitles.json
  3. generate the translated gameplay ActionScript
  4. generate the translated baked UI text tags + the CJK font subsets
  5. splice everything back into the SWF and compile

Usage:
    uv run python pipeline/build.py [--orig <game.swf>]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FFDEC = ROOT / "tools" / "ffdec" / "ffdec-cli.jar"
DEFAULT_ORIG = ROOT / "dist" / "Road-Of-The-Dead.swf"
WORK = ROOT / "work"


def run(cmd: list[str], label: str) -> None:
    print(f"\n== {label}")
    proc = subprocess.run(cmd, cwd=str(ROOT))
    if proc.returncode != 0:
        raise SystemExit(f"{label} failed ({proc.returncode})")


def py(*args: str) -> list[str]:
    return ["uv", "run", "python", *args]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--orig", default=str(DEFAULT_ORIG))
    ap.add_argument("--skip-export", action="store_true")
    args = ap.parse_args()

    if not FFDEC.exists():
        raise SystemExit(
            f"FFDec not found at {FFDEC}\n"
            "see README.md -> 'Tools' for how to fetch it"
        )

    if not args.skip_export:
        WORK.mkdir(parents=True, exist_ok=True)
        run(
            ["java", "-Xmx4g", "-jar", str(FFDEC),
             "-export", "script,text,symbolClass", str(WORK / "scripts"), args.orig],
            "export scripts/texts",
        )

    run(py("pipeline/make_dtsound.py", "--out", "patch/DTSound.as"), "DTSound (subtitles)")
    run(py("pipeline/patch_as3.py"), "gameplay ActionScript")
    run(py("pipeline/build_ui.py"), "UI text tags")

    charset = WORK / "ui_charset.txt"
    # Two faces, matching the two faces the original uses: Dirty Ego for the
    # decorative menu/HUD text, Modern No. 20 (a high-contrast didone) for body.
    display_font = ROOT / "data" / "fonts" / "RoadOfTheDeadCN.ttf"
    body_font = ROOT / "data" / "fonts" / "NotoSerifSC-SemiBold.ttf"
    for label, path in (("display (Dirty Ego)", display_font),
                        ("body (Modern No. 20)", body_font)):
        if not path.exists():
            raise SystemExit(f"{label} font not found: {path}")
    (WORK / "fonts").mkdir(parents=True, exist_ok=True)
    run(
        ["uv", "run", "pyftsubset", str(display_font),
         f"--text-file={charset}", f"--output-file={WORK / 'fonts' / 'ui_cjk.ttf'}",
         "--no-hinting", "--desubroutinize", "--drop-tables+=DSIG"],
        "display CJK subset ui_cjk.ttf",
    )
    run(
        ["uv", "run", "pyftsubset", str(body_font),
         f"--text-file={charset}", f"--output-file={WORK / 'fonts' / 'ui_body.ttf'}",
         "--no-hinting", "--desubroutinize", "--drop-tables+=DSIG"],
        "body CJK subset ui_body.ttf",
    )

    run(py("pipeline/build_all.py", "--orig", args.orig), "splice + compile")
    print(f"\ndone -> {ROOT / 'dist' / 'rotl-zh-full.swf'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

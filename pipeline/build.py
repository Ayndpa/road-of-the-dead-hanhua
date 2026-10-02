"""Full pipeline: original SWF -> localised SWF.

Steps
  1. export scripts / texts / symbol classes with FFDec
  2. generate the subtitle-instrumented DTSound.as from the ParaTranz export
  3. generate the translated gameplay ActionScript
  4. generate the translated baked UI text tags + the CJK font subsets
  5. splice everything back into the SWF and compile

Translations are read from `data/paratranz/*.csv` (see pipeline/translations.py);
drop the files downloaded from the ParaTranz project in there to rebuild.

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

    # build_all.py now derives the per-face charsets, instantiates the Noto Sans
    # SC weights and subsets every CJK face itself (see the font map there).
    run(py("pipeline/build_all.py", "--orig", args.orig), "splice + compile")
    print(f"\ndone -> {ROOT / 'dist' / 'rotl-zh-full.swf'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

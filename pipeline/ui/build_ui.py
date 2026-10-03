"""Prepare translated UI text files and the CJK font subsets they need."""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline.lib.translations import UI_TRANSLATIONS  # noqa: E402
from pipeline.ui.menu_labels import MENU_LABELS  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SEP = "--- RECORDSEPARATOR ---"


def build_file(segments: list[str]) -> str:
    out = ""
    for i, s in enumerate(segments):
        if i:
            out += "\n" + SEP + "\n"
        out += s
    return out


def split_file(text: str) -> list[str]:
    return text.split(SEP)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", default=str(ROOT / "work" / "scripts" / "texts"))
    ap.add_argument("--out", dest="dst", default=str(ROOT / "work" / "ui_texts"))
    ap.add_argument("--charset", default=str(ROOT / "work" / "ui_charset.txt"))
    args = ap.parse_args()

    src = Path(args.src)
    dst = Path(args.dst)
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)

    translated = 0
    mismatch = []
    for p in sorted(src.glob("*.txt"), key=lambda q: int(q.stem)):
        raw = p.read_text(encoding="utf-8")
        segs = UI_TRANSLATIONS.get(p.stem)
        if segs is None:
            (dst / p.name).write_text(raw, encoding="utf-8")
            continue
        orig = split_file(raw)
        if len(orig) != len(segs):
            mismatch.append((p.stem, len(orig), len(segs)))
            (dst / p.name).write_text(raw, encoding="utf-8")
            continue
        (dst / p.name).write_text(build_file(segs), encoding="utf-8")
        translated += 1

    print(f"translated {translated}/{len(list(src.glob('*.txt')))} texts")
    if mismatch:
        print("!! segment count mismatch (left untranslated):")
        for cid, a, b in mismatch:
            print(f"   {cid}: original={a} translation={b}")

    chars = set()
    for p in dst.glob("*.txt"):
        chars |= set(p.read_text(encoding="utf-8"))
    # runtime text drawn by ActionScript uses the same embedded fonts
    for p in (ROOT / "patch" / "as3").glob("*.as"):
        chars |= set(p.read_text(encoding="utf-8"))
    # main-menu vector labels redrawn with the CJK UI font
    for text, _color, _opacity in MENU_LABELS.values():
        chars |= set(text)
    ascii_extra = set(chr(c) for c in range(0x20, 0x7F))
    chars |= ascii_extra
    chars.discard("\n")
    chars.discard("\r")
    Path(args.charset).write_text("".join(sorted(chars)), encoding="utf-8")
    print(f"charset: {len(chars)} chars -> {args.charset}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

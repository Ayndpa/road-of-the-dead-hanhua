"""Extract Road of the Dead 2 user-visible text into ParaTranz source CSVs.

Mirrors the ROTD1 layout (``data/paratranz/*.csv``) so the same build steps can
consume ``data/paratranz2/*.csv`` through ``ROT_TRANSLATIONS``:

    ui.csv    ui_<DefineText id>     baked DefineText / DefineEditText text
    as3.csv   as3_<file>_<n>         runtime ActionScript string literals
    voice.csv SND_*                  voice sound classes (original filled by ASR)

The original column is left as the decompiled English; the translation column is
empty for a translator (or machine translation) to fill.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK2 = ROOT / "work2"
TEXTS = WORK2 / "scripts" / "texts"
SCRIPTS = WORK2 / "scripts" / "scripts"
LITERALS = WORK2 / "as3_literals.json"
OUT = ROOT / "data" / "paratranz2"

SEP = "--- RECORDSEPARATOR ---"
LAT = re.compile(r"[A-Za-z]{2,}")


def write_csv(name: str, header: str, rows: list[list[str]]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    with path.open("w", encoding="utf-8", newline="") as fh:
        fh.write(header + "\n")
        csv.writer(fh).writerows(rows)
    print(f"{name}: {len(rows)} rows -> {path}")


def extract_ui() -> None:
    rows = []
    for p in sorted(TEXTS.glob("*.txt"), key=lambda q: int(q.stem)):
        raw = p.read_text(encoding="utf-8")
        joined = raw.replace(SEP, "")
        if not LAT.search(joined):
            continue
        original = joined.strip("\r\n").rstrip()
        rows.append([f"ui_{p.stem}", original, "", f"DefineText {p.stem}"])
    write_csv("ui.csv", "key,original,translation,context", rows)


def extract_as3() -> None:
    data: dict[str, list[str]] = json.loads(LITERALS.read_text(encoding="utf-8"))
    rows = []
    for rel, literals in sorted(data.items()):
        safe = rel.replace("\\", "/").replace("/", "_").removesuffix(".as")
        for i, lit in enumerate(sorted(set(literals)), 1):
            rows.append([f"as3_{safe}_{i}", lit, "", rel])
    write_csv("as3.csv", "key,original,translation,context", rows)


def extract_voice() -> None:
    rows = []
    for p in sorted(SCRIPTS.rglob("SND_*.as")):
        rows.append([p.stem, "", "", "voice"])
    write_csv("voice.csv", "key,original,translation,context", rows)


def main() -> int:
    extract_ui()
    extract_as3()
    extract_voice()
    return 0


if __name__ == "__main__":
    sys.exit(main())

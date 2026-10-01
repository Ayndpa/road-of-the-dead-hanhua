"""Scan decompiled AS3 for string literals that look user-facing."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "work" / "scripts" / "scripts"

LIT = re.compile(r'"((?:[^"\\\n]|\\.){10,})"')
SENTENCE = re.compile(r"[A-Za-z]{3,}\s+[A-Za-z]{2,}")
SKIP = re.compile(
    r"(\.as$|::|getDefinitionByName|addFrameScript|_assets|SND_|^MC_|fla\.|"
    r"^[A-Za-z_]+$|\.png$|\.mp3$|^https?:|font|Font|TextField|TextFieldAutoSize)"
)


def main() -> int:
    only = sys.argv[1] if len(sys.argv) > 1 else ""
    hits: dict[str, list[tuple[int, str]]] = {}
    for p in sorted(SRC.rglob("*.as")):
        rel = str(p.relative_to(SRC))
        if "newgrounds" in rel.lower():
            continue
        if only and only.lower() not in rel.lower():
            continue
        txt = p.read_text(encoding="utf-8", errors="replace")
        for m in LIT.finditer(txt):
            s = m.group(1)
            if not SENTENCE.search(s):
                continue
            if SKIP.search(s):
                continue
            line = txt.count("\n", 0, m.start()) + 1
            hits.setdefault(rel, []).append((line, s))
    total = sum(len(v) for v in hits.values())
    print(f"candidate user-facing strings: {total} in {len(hits)} files")
    for f, v in hits.items():
        print(f"== {f} ({len(v)})")
        for line, s in v:
            print(f"  {line}: {s[:160]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

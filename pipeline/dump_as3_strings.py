"""Extract real AS3 string literals (proper tokenizer, escapes aware)."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "work" / "scripts" / "scripts"


def iter_literals(text: str):
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            i = n if j < 0 else j + 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        if c == '"':
            j, buf = i + 1, []
            while j < n:
                if text[j] == "\\" and j + 1 < n:
                    buf.append(text[j : j + 2])
                    j += 2
                    continue
                if text[j] == '"':
                    break
                buf.append(text[j])
                j += 1
            line = text.count("\n", 0, i) + 1
            yield line, "".join(buf)
            i = j + 1
            continue
        i += 1


FILES = [
    "BasicGame.as",
    "Input.as",
    "RDAchievement.as",
    "RDGame.as",
    "RDGameModeGameplay.as",
    "RDGameModeGarage.as",
    "RDGameModeMilitary.as",
    "RDGameModeStory.as",
    "RDGameModeTime.as",
    "RDUnlockItem.as",
    "RDPlayerInfo.as",
    "RDHud.as",
    "RDGameModeMenu.as",
]

WORDS = re.compile(r"[A-Za-z]{3,}")


def main() -> int:
    out: dict[str, list[dict]] = {}
    for name in FILES:
        p = SRC / name
        if not p.exists():
            continue
        txt = p.read_text(encoding="utf-8", errors="replace")
        rows = []
        for line, s in iter_literals(txt):
            if not s or not WORDS.search(s):
                continue
            if s.startswith("http") or s in ("_blank",):
                continue
            rows.append({"line": line, "text": s})
        out[name] = rows
    dst = ROOT / "work" / "as3_strings.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{sum(len(v) for v in out.values())} literals -> {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

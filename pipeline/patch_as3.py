"""Patch user-facing English literals inside the gameplay ActionScript.

The literal -> Chinese table comes straight from the ParaTranz export
(``data/paratranz/as3.csv``, grouped by the ``context`` column = file name).
Only rows whose original still appears in the decompiled source are applied, so
a stale or extra entry is reported instead of silently mangling the code.

Replacement is done on the exact decompiled source text, so the keys must match
what FFDec emitted (including ``\\n`` / ``\\'`` escapes).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "work" / "scripts" / "scripts"
DST = ROOT / "patch" / "as3"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from translations import AS3 as T  # noqa: E402


def main() -> int:
    DST.mkdir(parents=True, exist_ok=True)
    report = {}
    for name, mapping in T.items():
        src = SRC / name
        txt = src.read_text(encoding="utf-8")
        applied, missing = 0, []
        for old, new in mapping.items():
            wrapped_old = f'"{old}"'
            wrapped_new = f'"{new}"'
            if wrapped_old in txt:
                txt = txt.replace(wrapped_old, wrapped_new)
                applied += 1
            elif old.startswith('"') and old.endswith('"'):
                # key already quoted (fragment without surrounding quotes)
                if old in txt:
                    txt = txt.replace(old, new)
                    applied += 1
                else:
                    missing.append(old)
            else:
                missing.append(old)
        if name == "BasicGame.as" and "DTSound.InitSubtitles();" not in txt:
            anchor = "         m_bGaveMedals = false;\n"
            if anchor in txt:
                txt = txt.replace(
                    anchor, anchor + "         DTSound.InitSubtitles();\n", 1
                )
        (DST / name).write_text(txt, encoding="utf-8")
        report[name] = (applied, len(mapping), missing)
        print(f"{name}: applied {applied}/{len(mapping)}")
        for m in missing:
            print(f"   !! not found: {m[:90]}")
    (ROOT / "work" / "as3_patch_report.json").write_text(
        json.dumps({k: {"applied": v[0], "total": v[1], "missing": v[2]} for k, v in report.items()},
                   ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

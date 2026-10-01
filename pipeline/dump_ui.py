"""Dump FFDec-exported text tags as charId + record segments (JSON)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

SEP = "--- RECORDSEPARATOR ---"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("texts")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    root = Path(args.texts)
    data: dict[str, list[str]] = {}
    for p in sorted(root.glob("*.txt"), key=lambda q: int(q.stem)):
        raw = p.read_text(encoding="utf-8")
        parts = raw.split(SEP)
        data[p.stem] = parts

    out = Path(args.out) if args.out else root.parent / "ui_segments.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"texts={len(data)} -> {out}")
    for cid, parts in data.items():
        if len(parts) > 1:
            print(f"[{cid}] {' | '.join(repr(x) for x in parts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

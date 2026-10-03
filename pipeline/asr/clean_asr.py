"""Clean a Whisper ASR result file: drop hallucinations and non-dialogue clips.

Reads the JSON produced by ``pipeline/asr/asr.py`` / ``asr_vulkan.py`` (keyed by
file, each value ``{cls, text, segments, duration, ...}``) and writes a copy
containing only usable dialogue, plus a TSV of the kept lines and a report of
everything that was dropped and why.

    uv run python pipeline/asr/clean_asr.py --asr work2/asr_gpu.json --out work2/asr_clean.json

By default clips whose *class name* is a non-dialogue sound (music, zombie,
impacts, guns, engines, ...) are dropped as well; pass ``--no-class-filter`` to
keep every class and only remove hallucinated text, or ``--keep REGEX`` to use
an allow-list of dialogue classes instead.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline.asr.asr_filter import NON_DIALOGUE_RE, UNNAMED_CLASS, is_hallucination  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--asr", default=str(ROOT / "work" / "asr_gpu.json"))
    ap.add_argument("--out", default="", help="cleaned json (default: <asr>_clean.json)")
    ap.add_argument("--tsv", default="", help="kept lines as cls<TAB>text (default: <out>.tsv)")
    ap.add_argument("--report", default="", help="dropped entries (default: <out>.dropped.json)")
    ap.add_argument("--no-class-filter", action="store_true", help="keep every class")
    ap.add_argument("--deny", default="", help="class regex to drop (overrides the default)")
    ap.add_argument("--keep", default="", help="class regex to keep (allow-list; overrides deny)")
    args = ap.parse_args()

    src = Path(args.asr)
    out = Path(args.out) if args.out else src.with_name(src.stem + "_clean.json")
    tsv = Path(args.tsv) if args.tsv else out.with_suffix(".tsv")
    report = Path(args.report) if args.report else out.with_suffix(".dropped.json")

    data = json.loads(src.read_text(encoding="utf-8"))
    deny = re.compile(args.deny) if args.deny else NON_DIALOGUE_RE
    keep = re.compile(args.keep) if args.keep else None

    cleaned: dict = {}
    dropped: list[dict] = []
    for fname, rec in data.items():
        cls, text = rec.get("cls", ""), rec.get("text", "")
        if not text.strip():
            dropped.append({"file": fname, "cls": cls, "text": text, "reason": "empty"})
        elif keep is not None and not keep.match(cls):
            dropped.append({"file": fname, "cls": cls, "text": text, "reason": "class"})
        elif keep is None and not args.no_class_filter and (
            deny.match(cls) or UNNAMED_CLASS.match(cls)
        ):
            dropped.append({"file": fname, "cls": cls, "text": text, "reason": "class"})
        elif is_hallucination(text):
            dropped.append({"file": fname, "cls": cls, "text": text, "reason": "hallucination"})
        else:
            cleaned[fname] = rec

    out.write_text(json.dumps(cleaned, ensure_ascii=False, indent=1), encoding="utf-8")
    report.write_text(
        json.dumps(dropped, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    rows = sorted((r["cls"], r["text"].strip()) for r in cleaned.values() if r["text"].strip())
    tsv.write_text("\n".join(f"{c}\t{t}" for c, t in rows), encoding="utf-8")

    n_class = sum(1 for d in dropped if d["reason"] == "class")
    n_hall = sum(1 for d in dropped if d["reason"] == "hallucination")
    n_empty = sum(1 for d in dropped if d["reason"] == "empty")
    print(
        f"total={len(data)} kept={len(cleaned)} "
        f"dropped={len(dropped)} (class={n_class}, hallucination={n_hall}, empty={n_empty})"
    )
    print(f"  kept  -> {out}")
    print(f"  lines -> {tsv} ({len(rows)} non-empty)")
    print(f"  report-> {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

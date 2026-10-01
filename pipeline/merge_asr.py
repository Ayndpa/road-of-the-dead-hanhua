"""Merge ASR result files (CPU + GPU shards) into one cache."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "inputs",
        nargs="*",
        default=[
            str(ROOT / "work" / "asr_results_cpu.json"),
            str(ROOT / "work" / "asr_gpu_shard0.json"),
            str(ROOT / "work" / "asr_gpu.json"),
            str(ROOT / "work" / "asr_results.json"),
        ],
    )
    ap.add_argument("--out", default=str(ROOT / "work" / "asr_all.json"))
    args = ap.parse_args()

    merged: dict = {}
    for p in args.inputs:
        path = Path(p)
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        new = 0
        for k, v in data.items():
            if k not in merged:
                merged[k] = v
                new += 1
        print(f"{path.name}: {len(data)} entries ({new} new)")
    out = Path(args.out)
    out.write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"merged {len(merged)} entries -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

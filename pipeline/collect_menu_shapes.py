"""Collect the main-menu / UI shapes into a folder for redrawing."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

OUT = ROOT / "menu-shapes"
SRC_PNG = ROOT / "work" / "shapepng"
SPRITES = ROOT / "work" / "sprites"

MENU_ROOTS = ["4291"]
EXTRA_SHAPES = ["4342", "4350", "4357", "4382", "4405", "4343", "4344"]


def leaves(root_ids: list[str]) -> list[tuple[str, str]]:
    res = subprocess.run(
        [sys.executable if False else "uv", "run", "python",
         str(ROOT / "pipeline" / "walk_sprite.py"),
         r"D:\Dev\Codes\Test\road-of-the-dead.swf", *root_ids],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    out = []
    for line in res.stdout.splitlines():
        line = line.strip().lstrip("- ").strip()
        parts = line.split()
        if len(parts) >= 2 and parts[1].startswith("DefineShape"):
            out.append((parts[0], parts[1]))
    return out


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    shapecode: dict[str, str] = {}
    for cid, kind in leaves(MENU_ROOTS):
        shapecode[cid] = kind
    for cid in EXTRA_SHAPES:
        shapecode.setdefault(cid, "extra")

    rows = []
    for cid in sorted(shapecode, key=int):
        p = SRC_PNG / f"{cid}.png"
        if not p.exists():
            continue
        from PIL import Image

        with Image.open(p) as im:
            w, h = im.size
        shutil.copy2(p, OUT / f"shape_{cid}.png")
        rows.append((cid, shapecode[cid], w, h))

    # reference renders
    for name in ("DefineSprite_4291", "DefineSprite_4358", "DefineSprite_4379", "DefineSprite_4431"):
        src = SPRITES / name / "1.png"
        if src.exists():
            shutil.copy2(src, OUT / f"render_{name}.png")

    man = OUT / "manifest.csv"
    man.write_text(
        "charId,kind,width,height\n" + "\n".join(f"{a},{b},{c},{d}" for a, b, c, d in rows),
        encoding="utf-8",
    )
    print(f"copied {len(rows)} shapes + reference renders -> {OUT}")
    for a, b, c, d in rows:
        print(f"  {a}: {b} {c}x{d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

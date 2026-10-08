"""Extract SWF ``PlaceObject3`` surface filters (glow / drop shadow) into
``assets/swf/filters.json`` so the runtime can reproduce them.

Flash lets a placed movie clip carry filters such as a black glow (used on the
main-menu buttons).  FFDec's raster/vector exports drop these, which is why the
ported menu lost the soft dark outline around the button text.  This tool reads
the decompiled SWF XML and records, per placed character id, the filter inputs.

Usage:
    python godot/exporter/export_filters.py --swf dist/Road-Of-The-Dead.swf
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FFDEC = ROOT / "tools" / "ffdec" / "ffdec-cli.jar"
DEFAULT_GODOT = ROOT / "godot"


def _rgba(tag: str) -> list[int]:
    def g(name: str, default: int) -> int:
        m = re.search(name + r'="(-?\d+)"', tag)
        return int(m.group(1)) if m else default
    return [g("red", 0), g("green", 0), g("blue", 0), g("alpha", 255)]


def _ensure_xml(swf: Path, java: str, ffdec: Path) -> Path:
    cached = Path(tempfile.gettempdir()) / "rotl_godot" / (swf.stem + ".xml")
    if cached.exists() and cached.stat().st_size > 1000:
        return cached
    cached.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([java, "-jar", str(ffdec), "-swf2xml", str(swf), str(cached)],
                   capture_output=True, text=True, cwd=str(ROOT), check=True)
    return cached


def parse_filters(xml: Path) -> dict:
    data = xml.read_text(encoding="latin1", errors="replace")
    out: dict[str, dict] = {}
    pat = re.compile(
        r'<item type="PlaceObject3Tag"[^>]*?characterId="(\d+)"[^>]*?>.{0,8000}?'
        r"<surfaceFilterList>(.*?)</surfaceFilterList>", re.S)
    for m in pat.finditer(data):
        cid = m.group(1)
        block = m.group(2)
        fx: dict = {}
        gm = re.search(r'<item type="GLOWFILTER"([^>]*)>(.*?)</item>', block, re.S)
        if gm:
            params, body = gm.group(1), gm.group(2)
            num = lambda n, d: float((re.search(n + r'="(-?[\d.]+)"', params) or [None, str(d)])[1])
            col = re.search(r"<glowColor[^>]*>", body)
            fx["glow"] = {
                "color": _rgba(col.group(0)) if col else [0, 0, 0, 255],
                "blur": (num("blurX", 5.0) + num("blurY", 5.0)) * 0.5,
                "strength": num("strength", 1.0),
            }
        dm = re.search(r'<item type="DROPSHADOWFILTER"([^>]*)>(.*?)</item>', block, re.S)
        if dm:
            params, body = dm.group(1), dm.group(2)
            num = lambda n, d: float((re.search(n + r'="(-?[\d.]+)"', params) or [None, str(d)])[1])
            col = re.search(r"<dropShadowColor[^>]*>", body)
            ang = num("angle", 0.0)
            dist = num("distance", 0.0)
            import math
            fx["drop"] = {
                "color": _rgba(col.group(0)) if col else [0, 0, 0, 255],
                "blur": (num("blurX", 4.0) + num("blurY", 4.0)) * 0.5,
                "strength": num("strength", 1.0),
                "off": [math.cos(ang) * dist, math.sin(ang) * dist],
            }
        if fx:
            out.setdefault(cid, {}).update(fx)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--swf", type=Path, default=ROOT / "dist" / "Road-Of-The-Dead.swf")
    ap.add_argument("--godot", type=Path, default=DEFAULT_GODOT)
    ap.add_argument("--ffdec", type=Path, default=DEFAULT_FFDEC)
    ap.add_argument("--java", default="java")
    args = ap.parse_args()

    xml = _ensure_xml(args.swf, args.java, args.ffdec)
    filters = parse_filters(xml)
    payload = {"meta": {"swf": args.swf.name, "count": len(filters)}, "filters": filters}
    out = args.godot / "assets" / "swf" / "filters.json"
    out.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    print(f"[filters] {len(filters)} filtered characters -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

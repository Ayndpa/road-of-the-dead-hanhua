#!/usr/bin/env python3
"""Export the garage hub audio into the Godot asset bundle.

The main asset bundle is produced by ``swf_to_godot.py``. Its ``--sounds``
list only names the sounds a given run needs, and ``sounds.json`` is
overwritten each run, so re-exporting the bundle drops the garage music,
chatter and upgrade feedback. Run this afterwards to add them back (or pass
the same class names to ``swf_to_godot.py`` via ``--sounds``):

    uv run python godot/exporter/export_garage_audio.py --swf dist/Road-Of-The-Dead.swf

Existing ``sounds.json`` entries are preserved; only the garage ids are
added or refreshed.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_FFDEC = REPO / "tools" / "ffdec" / "ffdec-cli.jar"
DEFAULT_SWF = REPO / "dist" / "Road-Of-The-Dead.swf"
DEFAULT_GODOT = REPO / "godot"

# See work/scripts/symbolClass/symbols.csv for the id -> class name mapping.
GARAGE_SOUND_IDS = [
    1152,  # SND_Music_GarageMusic
    1336,  # SND_UpgradePerception
    1146,  # SND_UpgradeBodyArmor
    1267, 1282,  # SND_UpgradeFirearm, SND_UpgradeFirearmBullet
    1364,  # SND_UpgradeWindshield
    1223, 1237, 1252,  # SND_UpgradeEngine1..3
    1161, 1176, 1191,  # SND_UpgradeBumper1..3
    1350,  # SND_UpgradeTire
    1295, 1309, 1322,  # SND_UpgradeHorn1..3
    1585,  # SND_PlayerFirstTimeInGarage
    1601,  # SND_ErrorSound
    # SND_GarageChatter01..20
    1145, 1160, 1175, 1190, 1206, 1222, 1236, 1251, 1266, 1281,
    1294, 1308, 1321, 1335, 1349, 1363, 1377, 1389, 1401, 1412,
]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--swf", type=Path, default=DEFAULT_SWF, help="source SWF")
    p.add_argument("--godot", type=Path, default=DEFAULT_GODOT, help="Godot project directory")
    p.add_argument("--ffdec", type=Path, default=DEFAULT_FFDEC, help="ffdec-cli.jar")
    p.add_argument("--java", default="java", help="java executable")
    return p


def main() -> None:
    args = build_parser().parse_args()
    if not args.ffdec.exists():
        raise SystemExit(f"FFDec not found at {args.ffdec}")
    if not args.swf.exists():
        raise SystemExit(f"SWF not found at {args.swf}")

    sounds_dir = args.godot / "assets" / "swf" / "sounds"
    sounds_dir.mkdir(parents=True, exist_ok=True)
    sounds_path = sounds_dir.parent / "sounds.json"

    sounds: dict = {}
    if sounds_path.exists():
        parsed = json.loads(sounds_path.read_text(encoding="utf-8"))
        if isinstance(parsed, dict):
            sounds = parsed

    ids = ",".join(str(i) for i in GARAGE_SOUND_IDS)
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [
            args.java, "-jar", str(args.ffdec),
            "-selectid", ids,
            "-format", "sound:mp3",
            "-export", "sound", tmp,
            str(args.swf),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            print(proc.stdout[-2000:])
            print(proc.stderr[-2000:], file=sys.stderr)
            raise SystemExit("FFDec sound export failed")
        exported = sorted(Path(tmp).rglob("*.mp3"))
        if not exported:
            raise SystemExit("FFDec produced no sound files")
        for src in exported:
            dst = sounds_dir / src.name
            dst.write_bytes(src.read_bytes())
            sid, name = src.stem.split("_", 1)
            sounds[sid] = {"name": name, "res": f"res://assets/swf/sounds/{src.name}"}

    ordered = {k: sounds[k] for k in sorted(sounds, key=lambda k: int(k))}
    sounds_path.write_text(json.dumps(ordered, separators=(",", ":")), encoding="utf-8")
    print(f"[garage] {len(exported)} sounds -> {sounds_path.relative_to(REPO)} ({len(ordered)} total)")


if __name__ == "__main__":
    main()

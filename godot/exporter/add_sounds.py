"""Add game SFX (DefineSound) to an already-exported Godot bundle.

Runs FFDec's sound:mp3 export for the requested DefineSound class names and
merges the results into assets/swf/sounds + sounds.json, without touching
characters.json / sprites / shapes (so the existing vector+bitmap bundle stays
intact).  Usage:

    uv run python godot/exporter/add_sounds.py \
        --swf dist/Road-Of-The-Dead.swf \
        --names SND_Music_GameMusic,SND_CarIdle1,...
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_SWF = REPO / "dist" / "Road-Of-The-Dead.swf"
DEFAULT_FFDEC = REPO / "tools" / "ffdec" / "ffdec-cli.jar"
DEFAULT_GODOT = REPO / "godot"

def _core_names() -> list:
	out: list = []
	# engine states per upgrade level
	for lvl in range(1, 5):
		for state in ("Idle", "Accel", "MaxSpeed", "DeccelNoBrake", "DeccelBrake"):
			out.append(f"SND_Car{state}{lvl}")
	out += ["SND_SmokingEngine", "SND_BurningEngine"]
	# collisions
	out += ["SND_BigCollision01", "SND_BigCollision02", "SND_BigCollision03",
		"SND_HardCollision01", "SND_HardCollision02", "SND_HardCollision03", "SND_HardCollision04",
		"SND_HardCollision05", "SND_HugeCollision01", "SND_HugeCollision02",
		"SND_MediumCollision01", "SND_MediumCollision02", "SND_MediumCollision03",
		"SND_MediumCollision04", "SND_MediumCollision05",
		"SND_LightCollision01", "SND_LightCollision02", "SND_LightCollision03",
		"SND_LightCollision04", "SND_LightCollision05", "SND_LightCollision06"]
	# humanoid hits / voices
	out += ["SND_HitZombie01", "SND_HitZombie02", "SND_HitZombie03", "SND_HitZombie04"]
	out += [f"SND_MaleZombieHit{i:02d}" for i in range(1, 11)]
	out += [f"SND_MaleZombieMoan{i:02d}" for i in range(1, 10)]
	out += [f"SND_MaleZombieGrunt{i:02d}" for i in range(1, 6)]
	out += [f"SND_MaleZombieLightGrunt{i:02d}" for i in range(1, 6)]
	out += [f"SND_MaleZombieAttack{i:02d}" for i in range(1, 14)]
	out += [f"SND_MaleZombieThreat{i:02d}" for i in range(1, 10)]
	out += [f"SND_MaleZombieGetOnHood{i:02d}" for i in range(1, 8)]
	out += [f"SND_FemaleZombieMoan{i:02d}" for i in range(1, 13)]
	out += [f"SND_FemaleZombieGrunt{i:02d}" for i in range(1, 16)]
	out += [f"SND_FemaleZombieAttack{i:02d}" for i in range(1, 7)]
	out += [f"SND_FemaleZombieCollision{i:02d}" for i in range(1, 5)]
	out += [f"SND_FemaleZombieThreat{i:02d}" for i in range(1, 4)]
	out += ["SND_IdleCling", "SND_RollOverSound", "SND_PunchWindshield", "SND_WindshieldBreak",
		"SND_HeavyWind", "SND_HitCivilianMale1", "SND_HitCivilianMale2", "SND_HitCivilianMale3",
		"SND_HitCivilianFemale1", "SND_HitCivilianFemale2", "SND_HitCivilianFemale3"]
	# hazards
	out += ["SND_TireBlow", "SND_TireBlownScraping", "SND_OilSlick", "SND_FenceHit",
		"SND_FeedersHit", "SND_ElectronicSignHit"]
	# player voice / death
	out += [f"SND_PlayerGruntSharp{i:02d}" for i in range(1, 15)]
	out += [f"SND_PlayerDeathZombie{i}" for i in range(1, 5)]
	out += [f"SND_PlayerDeathCrash{i}" for i in range(1, 5)]
	# weapons
	out += ["SND_PistolShot", "SND_BulletHitFlesh01", "SND_BulletHitFlesh02", "SND_BulletHitFlesh03"]
	# horn
	out += ["SND_Horn1", "SND_Horn2", "SND_Horn3", "SND_Horn4",
		"SND_CarHornSmall", "SND_CarHornMedium", "SND_CarHornLarge"]
	# checkpoints (radio comms)
	for i in range(0, 11):
		for part in ("Pre", "Post"):
			if i == 0 and part == "Pre":
				continue
			out.append(f"SND_CheckPoint{i}{part}")
	# music
	out += ["SND_Music_GameMusic", "SND_Music_MenuMusic", "SND_Music_GarageMusic"]
	return out


CORE_NAMES = _core_names()


def main() -> None:
	ap = argparse.ArgumentParser()
	ap.add_argument("--swf", type=Path, default=DEFAULT_SWF)
	ap.add_argument("--godot", type=Path, default=DEFAULT_GODOT)
	ap.add_argument("--ffdec", type=Path, default=DEFAULT_FFDEC)
	ap.add_argument("--java", default="java")
	ap.add_argument("--xml", type=Path)
	ap.add_argument("--names", help="optional extra comma list of class names / ids")
	args = ap.parse_args()

	godot_dir = args.godot.resolve()
	swf_dir = godot_dir / "assets" / "swf"
	snd_dir = swf_dir / "sounds"
	snd_dir.mkdir(parents=True, exist_ok=True)
	sounds_json = swf_dir / "sounds.json"
	existing: dict = {}
	if sounds_json.exists():
		existing = json.loads(sounds_json.read_text(encoding="utf-8"))

	names: set[str] = set()
	for n in CORE_NAMES:
		names.add(n if n.startswith("SND_") else f"SND_{n}")
	if args.names:
		for token in args.names.split(","):
			token = token.strip()
			if token:
				names.add(token)

	# resolve class name -> DefineSound char id via the cached SWF XML
	xml = args.xml
	if xml is None:
		xml = Path(tempfile.gettempdir()) / "rotl_godot" / f"{args.swf.stem}.xml"
	if not xml.exists():
		xml.parent.mkdir(parents=True, exist_ok=True)
		print(f"[xml] dumping {args.swf.name} -> {xml} ...")
		proc = subprocess.run([args.java, "-Xmx4g", "-jar", str(args.ffdec),
			"-swf2xml", str(args.swf), str(xml)], capture_output=True, text=True)
		if proc.returncode != 0 or not xml.exists():
			print(proc.stdout[-2000:])
			print(proc.stderr[-2000:], file=sys.stderr)
			sys.exit("swf2xml failed")
	name_to_id: dict[str, str] = {}
	text = xml.read_text(encoding="utf-8", errors="ignore")
	# FFDec XML SymbolClassTag: <tags><item>ID</item>...</tags><names><item>NAME</item>...</names>
	# (nested <item> elements, so slice blocks by the next top-level <item type=...)
	marks = [m.start() for m in re.finditer(r'<item[^>]*type="[A-Za-z]+Tag"', text)]
	marks.append(len(text))
	for k in range(len(marks) - 1):
		seg = text[marks[k]:marks[k + 1]]
		if 'type="SymbolClassTag"' not in seg[:60]:
			continue
		tags_m = re.search(r"<tags>(.*?)</tags>", seg, re.S)
		names_m = re.search(r"<names>(.*?)</names>", seg, re.S)
		if not tags_m or not names_m:
			continue
		tags = re.findall(r"<item>(\d+)</item>", tags_m.group(1))
		nm = re.findall(r"<item>([^<]+)</item>", names_m.group(1))
		for cid, name in zip(tags, nm):
			name_to_id.setdefault(name, cid)
	if not name_to_id:
		sys.exit("no SymbolClassTag entries found in XML")

	wanted: dict[str, str] = {}
	for n in sorted(names):
		cid = name_to_id.get(n)
		if cid is None:
			print(f"[skip] {n}: no DefineSound/SymbolClass entry")
			continue
		wanted[n] = cid
	print(f"[sound] exporting {len(wanted)} sounds")

	tmp = Path(tempfile.mkdtemp(prefix="rotl_snd_"))
	cmd = [args.java, "-jar", str(args.ffdec), "-selectid", ",".join(sorted(set(wanted.values()))),
		"-format", "sound:mp3", "-export", "sound", str(tmp), str(args.swf)]
	proc = subprocess.run(cmd, capture_output=True, text=True)
	if proc.returncode != 0:
		print(proc.stdout[-3000:])
		print(proc.stderr[-3000:], file=sys.stderr)
		sys.exit("ffdec sound export failed")

	# ffdec names files <id>.mp3 (or <id>_<n>.mp3)
	exported: dict[str, str] = {}
	for p in tmp.rglob("*.mp3"):
		head = p.name.split("_")[0].split(".")[0]
		if head.isdigit():
			exported.setdefault(head, str(p))

	merged = dict(existing)
	missing = []
	for n, cid in sorted(wanted.items()):
		src = exported.get(cid)
		if src is None:
			missing.append(n)
			continue
		dst = snd_dir / f"{cid}.mp3"
		shutil.copyfile(src, dst)
		merged[cid] = {"name": n, "res": f"res://assets/swf/sounds/{cid}.mp3"}
	sounds_json.write_text(json.dumps(merged, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
	print(f"[sound] merged -> {sounds_json} (total {len(merged)})")
	if missing:
		print(f"[sound] {len(missing)} not found in SWF, e.g. {missing[:8]}")


if __name__ == "__main__":
	main()

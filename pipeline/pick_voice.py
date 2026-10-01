"""Pick dialogue-bearing voice clips out of the ASR results.

Whisper hallucinates short phrases ("Thank you for watching") on music and
sound effects, so selection is driven by the sound's class name, which the
original developers named very descriptively.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASR = ROOT / "work" / "asr_results.json"

# Classes whose *class name* says they carry spoken dialogue.
VOICE_RE = re.compile(
    r"^SND_("
    r"CheckPoint\d+(Pre|Post)"
    r"|Jet(Dispatch|MissAndLeave|MissAndRepeat|Hit|PassBy)\d*"
    r"|Helicopter(Dispatch|MissileRequest|Warning|Defeated)\d*"
    r"|HelicopterBrokenAlert"
    r"|GarageChatter\d+"
    r"|Approach(Align|Bomb|Hidden|Spike|Stationary)Soldier\d+"
    r"|JohnSoldier(GetOff|HardGrunt|LightGrunt|Threat)\d+"
    r"|Soldier(GetOff|HardGrunt|LightGrunt|Threat)\d+"
    r"|(Fe)?MaleCivilian\d*(Plea|Hit)\d+"
    r"|PlayerFirstTimeInGarage"
    r"|PlayerDeath(Crash|Helicopter|Jet|Military|Nuke|Zombie)?"
    r"|Player(Devoured|FatalBullet|ExtinguishFire|BlownTires|Fire|GunEmpty)"
    r"|Player(HelicopterReaction|HoodEnemyReaction|JetReaction|HitCiv|HitEnemy|ShootHoodEnemy|PreciseHit|NoAmmo|NoGun)"
    r"|Upgrade(BodyArmor|Bumper|Engine|Firearm|FirearmBullet|Horn|Perception|Tire|Windshield)"
    r"|PlayerUpgrade(BodyArmor|Bumper|Engine|Firearm|Horn|Perception|Tires|Windshield)"
    r"|NukeRunCount(Start|\d+)"
    r"|FailStringer_1_V4"
    r")\d*$"
)

# Human-vocalisation-only classes (screams/grunts) that never need subtitles.
NOISE_RE = re.compile(
    r"^SND_(Player(Grunt|HeavyGrunt|LightGrunt|MediumGrunt)|JohnSoldier\w*Grunt|Soldier\w*Grunt|"
    r"MaleZombie|FemaleZombie|SuperZombie|HitZombie|Feeders|IdleCling)"
)

HALLUCINATIONS = re.compile(
    r"(thank you for watching|thanks for watching|transcription by|translation by|"
    r"subtitles? by|amara\.org|subtitle|subscribe|www\.|\.com)",
    re.IGNORECASE,
)


def is_hallucination(text: str) -> bool:
    if not text:
        return True
    stripped = text.strip()
    if HALLUCINATIONS.search(stripped):
        return True
    # nothing but punctuation/symbols
    if re.fullmatch(r"[\W_]+", stripped):
        return True
    # a single character repeated over and over (screams, "RRRRR", "AAAA")
    core = re.sub(r"[\W_]", "", stripped)
    if len(core) >= 8 and len(set(core)) <= 2:
        return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--asr", default=str(ASR))
    ap.add_argument("--out", default=str(ROOT / "work" / "voice_lines.json"))
    ap.add_argument("--tsv", default=str(ROOT / "work" / "voice_lines.tsv"))
    ap.add_argument("--all", action="store_true", help="dump every class")
    args = ap.parse_args()

    data = json.loads(Path(args.asr).read_text(encoding="utf-8"))
    picked: dict[str, dict] = {}
    rejected: list[dict] = []
    rows: list[tuple[str, str, float, str]] = []
    for fname, rec in data.items():
        cls = rec["cls"]
        if not args.all:
            if not VOICE_RE.match(cls):
                continue
            if NOISE_RE.match(cls):
                continue
        entry = {
            "file": fname,
            "text": rec["text"],
            "duration": rec["duration"],
            "segments": rec.get("segments", []),
            "hallucination": is_hallucination(rec["text"]),
        }
        rows.append((cls, fname, rec["duration"], rec["text"]))
        if entry["hallucination"]:
            rejected.append({"cls": cls, **entry})
        else:
            picked[cls] = entry

    rows.sort()
    Path(args.tsv).write_text(
        "\n".join(f"{c}\t{dur:.1f}\t{t}" for c, _, dur, t in rows), encoding="utf-8"
    )

    out = Path(args.out)
    out.write_text(json.dumps(picked, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"picked={len(picked)} rejected={len(rejected)} -> {out}")
    print("--- rejected (candidate but unusable) ---")
    for r in rejected:
        print(f"  {r['cls']}: {r['text'][:70]!r} ({r['duration']}s)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

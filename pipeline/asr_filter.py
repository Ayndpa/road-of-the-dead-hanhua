"""Text-side cleanup for Whisper ASR output.

Whisper invents phrases on music and silence ("Thank you for watching",
"Subtitles by ...", runs of music notes) and mis-hears sound effects as words
("*Gunshot*", "Hello, hello" over a growl).  Two independent layers remove them:

* :func:`is_hallucination` -- a content test: known hallucination phrases,
  music notation, a string that is nothing but a bracketed sound tag,
  punctuation-only output, and one character screamed into a long run.
* :data:`NON_DIALOGUE_RE` -- a class-name test for sounds that never carry
  dialogue (music, zombie vocals, impacts, guns, engines, sirens, ...).  It is
  game-specific; callers can pass their own pattern instead.

Both are deliberately conservative: legit short lines such as "No, no, no!" or
"Thanks! You're amazing!" must survive, so the repeat test only fires on a run
of the *same* character and the phrase list stays to unmistakable artifacts.
"""
from __future__ import annotations

import re

HALLUCINATIONS = re.compile(
    r"("
    r"thank you for watching|thanks for watching|we'?ll be right back|"
    r"transcription by|translation by|subtitles? by|amara\.org|"
    r"please (like and )?subscribe|www\.|\.com"
    r")",
    re.IGNORECASE,
)

MUSIC_NOTES = re.compile(r"[\u2669-\u266f]")

# one or more bracketed sound tags and nothing else: *Growl*, *Grunts* *Groans*
BRACKET_TAG = re.compile(r"^(?:[*\[(][^*\])]*[*\])]\s*)+$")

# the whole text is a single character repeated 5+ times: AAAAAA, NOOOOOO
REPEATED = re.compile(r"^[\W_]*(\w)\1{4,}[\W_]*$", re.IGNORECASE)

# Class names whose clips are sounds, not speech.  Anchored on the class, so
# "SND_PassingCar..." (dialogue) is not caught by the "Car" rule.
NON_DIALOGUE_RE = re.compile(
    r"^SND_("
    r"Music_|Horror"
    r"|(Melee|Male|Female|Super|Alpha|Hit)?Zombie|Feeders|IdleCling"
    r"|Bullet|HitZombie"
    r"|.*Collision|.*Explosion|NukeNoise|FenceHit|ShoppingCartHit|Traffic|WaterJug"
    r"|ElectronicSignHit|SideScraping|Punch|Windshield|SideWindow|Tire|OilSlick"
    r"|SpikeSlide|Horn|ButtonSound|ErrorSound|AmmoSound|RollOverSound"
    r"|.*Siren|HeavyWind|.*Step|ZombieLand|ZombieJump|MountedMG|MAC11|RocketLaunch"
    r"|MenuExplosion|SuperZombieCue|TankCar|Burning|SmokingEngine|.*Engine|.*Grunt"
    r"|Car\w"
    r")"
)


# Classes with no name at all (FFDec exports them as "<id>.mp3") are sounds with
# no dialogue: the audio script keys them by a bare numeric character id.
UNNAMED_CLASS = re.compile(r"^\d+$")


def is_hallucination(text: str) -> bool:
    """True for output that is not usable dialogue."""
    t = (text or "").strip()
    if not t:
        return True
    if HALLUCINATIONS.search(t):
        return True
    if MUSIC_NOTES.search(t):
        return True
    if BRACKET_TAG.match(t):
        return True
    core = re.sub(r"[\W_]", "", t)
    if not core or re.fullmatch(r"[\W_]+", t):
        return True
    if REPEATED.search(t):
        return True
    # a single token made of one or two letters, e.g. "HOOOOOO", "nononono"
    if " " not in t and len(core) >= 8 and len(set(core.lower())) <= 2:
        return True
    return False

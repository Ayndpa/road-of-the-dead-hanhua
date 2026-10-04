"""Read the project's translations from the ParaTranz CSV export.

Every user-visible Chinese string lives in ``data/paratranz/*.csv`` -- the very
files uploaded to and downloaded from the ParaTranz project
<https://paratranz.cn/projects/20958>.  The layout is ParaTranz's standard CSV:
``key,original,translation[,context]`` (no header row).  Download the project's
files from the platform, drop them into that folder, and the build applies them
directly -- there is no second copy of the translations inside the source tree.

Files:
    voice.csv   SND_* class name  -> voice subtitle
    stream.csv  stream_NN         -> opening streamed-audio subtitle
    ui.csv      ui_<DefineText id> -> baked UI text (records joined by "\\n")
    as3.csv     filename          -> {English literal: Chinese} for runtime text
    menu.csv    <label name>      -> main-menu vector label text

Set ``ROT_TRANSLATIONS`` to point at another folder (e.g. a freshly downloaded
export) without touching the checked-in files.
"""
from __future__ import annotations

import csv
import os
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DIR = ROOT / "data" / "paratranz"

# The platform's CSV importer ignores rows whose first cell starts with '#' and
# re-emits any header it was given; skip both so a round-tripped export parses.
_HEADER_CELLS = {"key", "keyvalue", "键值", "键"}


def translations_dir() -> Path:
    return Path(os.environ.get("ROT_TRANSLATIONS", DEFAULT_DIR))


@lru_cache(maxsize=None)
def load(name: str) -> dict[str, dict[str, str]]:
    """Load ``<name>.csv`` as ``{key: {original, translation, context}}``."""
    path = translations_dir() / f"{name}.csv"
    table: dict[str, dict[str, str]] = {}
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.reader(fh):
            if not row or not row[0].strip():
                continue
            key = row[0]
            if key.lstrip().startswith("#") or key.strip().lower() in _HEADER_CELLS:
                continue
            table[key] = {
                "original": row[1] if len(row) > 1 else "",
                "translation": row[2] if len(row) > 2 else "",
                "context": row[3] if len(row) > 3 else "",
            }
    return table


def strings(name: str) -> dict[str, str]:
    """``{key: translation}`` for every translated entry of ``<name>.csv``."""
    return {k: v["translation"] for k, v in load(name).items() if v["translation"]}


def pairs(name: str) -> dict[str, tuple[str, str]]:
    """``{key: (original, translation)}`` for every translated entry.

    The subtitle system keeps both languages so the player can toggle between
    English, Chinese and bilingual display; the English side is the platform's
    ``original`` column.
    """
    return {k: (v["original"], v["translation"])
            for k, v in load(name).items() if v["translation"]}


def _ui_translations() -> dict[str, list[str]]:
    """``{DefineText id: [record, ...]}`` rebuilt from the translation column.

    ``ui.csv`` stores each tag's records joined with a newline; the records are
    plain text with no embedded newlines, so the split is exact.
    """
    out: dict[str, list[str]] = {}
    for key, row in load("ui").items():
        if row["translation"] == "":
            continue
        # The platform keys are namespaced (``ui_3953``); the build keys its text
        # tags by their bare DefineText id.
        if key.startswith("ui_"):
            key = key[3:]
        out[key] = row["translation"].split("\n")
    return out


# AS3 literals that are *engine control values*, not user-visible text.  The
# Newgrounds classes compare them against fixed English case labels
# (``APIConnector._apiConnect`` switches on ``debugMode``; ``initAd`` switches
# on ``connectorType``).  Translating them makes the component fall through to
# its default -- ``debugMode`` "Off" -> ``RELEASE_MODE`` -- which drops the
# simulated user session and makes the passport/login prompt pop up on every
# launch of ROTD2.  Keyed by (context, original) so only these exact values are
# skipped; see ``data/paratranz2/as3.csv``.
_NON_TRANSLATABLE_AS3 = {
    ("RoadOfTheDead_fla\\MainTimeline.as", "Flash Ad Only"),
    ("RoadOfTheDead_fla\\MainTimeline.as", "Simulate Logged-in User"),
}


def _as3_translations() -> dict[str, dict[str, str]]:
    """``{filename: {original literal: translation}}`` for the runner patch."""
    out: dict[str, dict[str, str]] = {}
    for row in load("as3").values():
        if not row["translation"]:
            continue
        if (row["context"], row["original"]) in _NON_TRANSLATABLE_AS3:
            continue
        out.setdefault(row["context"], {})[row["original"]] = row["translation"]
    return out


# Imported by the build steps (build_all / align_controls / build_ui).
UI_TRANSLATIONS: dict[str, list[str]] = _ui_translations()
VOICE: dict[str, str] = strings("voice")
STREAM: dict[str, str] = strings("stream")
MENU: dict[str, str] = strings("menu")
AS3: dict[str, dict[str, str]] = _as3_translations()

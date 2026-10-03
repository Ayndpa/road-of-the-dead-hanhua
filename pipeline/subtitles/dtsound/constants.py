"""Shared paths and record separators for the DTSound subtitle builder.

The separators are single control characters embedded in the generated AS3
string data.  ``pipeline.lib.translations`` lives under the repository root, so
this module puts that root on ``sys.path`` however the builder is launched.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ORIGINAL = ROOT / "work" / "scripts" / "scripts" / "DTSound.as"

REC_SEP = "\x02"   # between entries
FLD_SEP = "\x01"   # between class name and text
SUB_SEP = "\x03"   # between timed sub-lines

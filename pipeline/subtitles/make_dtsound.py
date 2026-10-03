"""Generate a patched DTSound.as that adds an in-game subtitle overlay.

The overlay is driven from DTSound.Play(): every sound played by the game's
sound system is looked up by its embedded class name (e.g. ``SND_CheckPoint1Post``)
in a subtitle table, and the Chinese line is shown at the bottom of the stage
for the duration of the clip.

Subtitles are injected as a pure-ASCII AS3 string literal (``\\uXXXX`` escapes)
so the source never depends on the compiler's text encoding.

The Chinese lines come from the ParaTranz export (``data/paratranz/voice.csv`` and
``stream.csv``); clip durations / speech segments still come from the ASR cache
(``data/asr_all.json``) and the streamed-audio timing from
``data/stream_timing.json``.

The implementation lives in the :mod:`dtsound` package; this module stays the
stable entry point and CLI:

    python pipeline/subtitles/make_dtsound.py --out patch/DTSound.as
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.subtitles.dtsound import (  # noqa: E402
    FLD_SEP,
    ORIGINAL,
    REC_SEP,
    ROOT,
    SUB_SEP,
    as3_literal,
    build_chunks,
    build_stream_chunks,
    build_timed_chunks,
    generate,
    main,
    swf_stage_size,
)

__all__ = [
    "ROOT",
    "ORIGINAL",
    "REC_SEP",
    "FLD_SEP",
    "SUB_SEP",
    "as3_literal",
    "build_chunks",
    "build_stream_chunks",
    "build_timed_chunks",
    "swf_stage_size",
    "generate",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())

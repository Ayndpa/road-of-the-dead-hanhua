"""DTSound subtitle builder.

Turns the ParaTranz export plus the ASR cache into a patched ``DTSound.as`` that
shows an in-game subtitle overlay.  The public entry points are :func:`generate`
(programmatic) and :func:`main` (CLI).
"""
from __future__ import annotations

from .constants import FLD_SEP, ORIGINAL, REC_SEP, ROOT, SUB_SEP
from .as3 import as3_literal, build_chunks, build_stream_chunks, chunk_literals
from .generate import generate, main
from .subtitles import build_timed_chunks
from .swf import swf_stage_size

__all__ = [
    "ROOT",
    "ORIGINAL",
    "REC_SEP",
    "FLD_SEP",
    "SUB_SEP",
    "as3_literal",
    "build_chunks",
    "build_stream_chunks",
    "chunk_literals",
    "build_timed_chunks",
    "swf_stage_size",
    "generate",
    "main",
]

"""Encode Python strings as pure-ASCII AS3 string-literal source.

Subtitles travel as ``\\uXXXX`` escaped literals so the generated source never
depends on the compiler's text encoding.  Long data is split into a ``+``-joined
list of literals, keeping each ``append`` short enough for the AS3 compiler.
"""
from __future__ import annotations

from collections.abc import Iterable

from .constants import FLD_SEP, REC_SEP


def as3_literal(text: str) -> str:
    """Encode a Python string as a pure-ASCII AS3 string literal body."""
    out = []
    for ch in text:
        o = ord(ch)
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif 32 <= o < 127:
            out.append(ch)
        else:
            out.append("\\u%04x" % o)
    return "".join(out)


def chunk_literals(pieces: Iterable[str], chunk_chars: int = 200) -> str:
    """Group already-escaped fragments into quoted literals joined with ``+``.

    Each returned literal is at least ``chunk_chars`` long (except the last);
    splitting keeps a single generated expression small while producing one
    stable string at runtime.
    """
    out: list[str] = []
    cur: list[str] = []
    n = 0
    for piece in pieces:
        cur.append(piece)
        n += len(piece)
        if n >= chunk_chars:
            out.append('"' + "".join(cur) + '"')
            cur = []
            n = 0
    if cur:
        out.append('"' + "".join(cur) + '"')
    return " + ".join(out) if out else '""'


def build_chunks(entries: list[tuple[str, str, str]], chunk_chars: int = 200) -> str:
    """Build a ``+``-joined list of AS3 string literals, splitting on char count.

    Each record is ``class \\x01 zh \\x01 en``; both languages are carried so the
    player can switch between English, Chinese and bilingual display at runtime.
    """
    pieces = [
        as3_literal(cls + FLD_SEP + zh + FLD_SEP + en + REC_SEP)
        for cls, zh, en in entries
    ]
    return chunk_literals(pieces, chunk_chars)


def build_stream_chunks(entries: list[dict], chunk_chars: int = 200) -> str:
    """Build AS3 literals for streamed-audio segments: start|end|zh|en records."""
    pieces = [
        as3_literal("%.3f%s%.3f%s%s%s%s%s" % (
            float(e["start"]),
            FLD_SEP,
            float(e["end"]),
            FLD_SEP,
            e["zh"],
            FLD_SEP,
            e["en"],
            REC_SEP,
        ))
        for e in entries
    ]
    return chunk_literals(pieces, chunk_chars)

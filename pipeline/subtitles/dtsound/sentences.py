"""Split Chinese and English dialogue into sentences.

Chinese and English do not break sentences the same way, so the two use
different splitters: Chinese ends on CJK punctuation, English has to avoid
cutting inside decimals (``64.7``) and abbreviations (``U.S.``).
"""
from __future__ import annotations

import re

SENT_RE = re.compile(r"[^。！？!?…]*[。！？!?…]+|[^。！？!?…]+$")
# Sentence-ending run in English originals. A naive ``[^.!?]*[.!?]`` split also
# cuts inside decimals ("64.7") and abbreviations ("U.S."), inventing extra
# English sentences. Those make English look "finer" than Chinese, so the
# Chinese line gets pinned to an earlier slot and lags the voice.
EN_END_RE = re.compile(r"[.!?…]+")

_EN_ABBREV = frozenset({
    "mr", "mrs", "ms", "dr", "st", "vs", "etc", "jr", "sr", "no", "gen",
    "sgt", "capt", "lt", "col", "cmdr", "adm", "rev", "hon", "prof",
    "inc", "ltd", "co", "u.s", "u.k", "a.m", "p.m",
})


def split_sentences(text: str) -> list[str]:
    return [p.strip() for p in SENT_RE.findall(text) if p.strip()]


def split_sentences_en(text: str) -> list[str]:
    """Split English dialogue on real sentence ends only.

    A ``.`` is not a sentence end when it sits between digits (``64.7``) or
    closes a known abbreviation (``U.S.``), and the punctuation run has to be
    followed by whitespace or the end of the text.
    """
    text = text.strip()
    if not text:
        return []
    out: list[str] = []
    start = 0
    for m in EN_END_RE.finditer(text):
        i, end = m.start(), m.end()
        if (text[i] == "." and 0 < i < len(text) - 1
                and text[i - 1].isdigit() and text[i + 1].isdigit()):
            continue
        word = re.search(r"([A-Za-z](?:[A-Za-z.]*[A-Za-z])?)\.$", text[:i + 1])
        if word and word.group(1).lower() in _EN_ABBREV:
            continue
        nxt = text[end:end + 1]
        if nxt and not nxt.isspace():
            continue
        out.append(text[start:end].strip())
        start = end
    rest = text[start:].strip()
    if rest:
        out.append(rest)
    return [p for p in out if p]

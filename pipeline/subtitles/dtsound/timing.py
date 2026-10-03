"""Word-level alignment of subtitle sentences to ASR speech segments.

The ASR pass yields the real speech windows of the English track.  Matching the
(cleaned) English sentences to the segment transcripts word-by-word lets each
sentence take the window of the words it actually contains, instead of a
proportional guess that drifts whenever a sentence is spoken faster or slower
than its text length suggests.
"""
from __future__ import annotations

import difflib
import re
from collections import Counter

_WORD_RE = re.compile(r"[A-Za-z0-9']+")


def _words(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def _sentence_segments(sents: list[str], segments: list[dict]) -> list[int] | None:
    """Map each sentence to the ASR segment its words best match.

    Word-level alignment against the ASR transcripts; returns ``None`` when the
    overlap is too weak to trust (caller then falls back to proportional order).
    """
    ref: list[tuple[str, int]] = []       # (word, segment index)
    for si, seg in enumerate(segments):
        for w in _words(str(seg.get("text") or "")):
            ref.append((w, si))
    drv: list[tuple[str, int]] = []       # (word, sentence index)
    for ti, s in enumerate(sents):
        for w in _words(s):
            drv.append((w, ti))
    if not ref or not drv:
        return None
    sm = difflib.SequenceMatcher(a=[w for w, _ in drv], b=[w for w, _ in ref],
                                 autojunk=False)
    votes: dict[int, list[int]] = {}
    matched = 0
    for a, b, size in sm.get_matching_blocks():
        for k in range(size):
            votes.setdefault(drv[a + k][1], []).append(ref[b + k][1])
            matched += 1
    if matched < max(3, len(drv) // 4):
        return None
    res: list[int | None] = [None] * len(sents)
    for ti, sis in votes.items():
        res[ti] = Counter(sis).most_common(1)[0][0]
    last = 0
    for ti in range(len(sents)):
        if res[ti] is None:
            nxt = next((j for j in range(ti + 1, len(sents)) if res[j] is not None), None)
            res[ti] = res[nxt] if nxt is not None else last
        if res[ti] < last:
            res[ti] = last
        last = res[ti]
    return [int(x) for x in res]


def _merged_segment_groups(sents: list[str],
                           segments: list[dict]) -> list[tuple[int, int]]:
    """Inclusive ``(lo, hi)`` ASR-segment ranges to show as one subtitle line.

    The recognizer splits speech at pauses, so one CSV sentence often covers
    several ASR windows. Showing one line per window repeats the sentence on the
    later window; instead those windows are merged into one line spanning them.
    Returns every segment exactly once, in order.
    """
    n = len(segments)
    if not sents or n == 0:
        return [(i, i) for i in range(n)]

    ref: list[tuple[str, int]] = []       # (word, segment index)
    for si, seg in enumerate(segments):
        for w in _words(str(seg.get("text") or "")):
            ref.append((w, si))
    drv: list[tuple[str, int]] = []       # (word, sentence index)
    for ti, s in enumerate(sents):
        for w in _words(s):
            drv.append((w, ti))
    if not ref or not drv:
        return [(i, i) for i in range(n)]
    sm = difflib.SequenceMatcher(a=[w for w, _ in drv], b=[w for w, _ in ref],
                                 autojunk=False)
    per_sent: dict[int, dict[int, int]] = {}
    for a, b, size in sm.get_matching_blocks():
        for k in range(size):
            counts = per_sent.setdefault(drv[a + k][1], {})
            si = ref[b + k][1]
            counts[si] = counts.get(si, 0) + 1
    hi_of = [-1] * n
    for counts in per_sent.values():
        # A sentence has to land with at least two words in two windows before
        # we merge them; a lone coincidental word must not join distant lines.
        hit = [si for si, c in counts.items() if c >= 2]
        if len(hit) >= 2:
            lo, hi = min(hit), max(hit)
            for x in range(lo, hi):
                hi_of[x] = max(hi_of[x], hi)
    groups: list[tuple[int, int]] = []
    i = 0
    while i < n:
        end = i
        j = i
        while j <= end:
            end = max(end, hi_of[j])
            j += 1
        groups.append((i, end))
        i = end + 1
    return groups

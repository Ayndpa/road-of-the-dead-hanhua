"""Align Chinese sentences to English sentences across ASR segments.

Chinese and English rarely break sentences at the same place.  Shared Latin or
numeric tokens (numbers, callsigns, place names) survive translation and pin a
Chinese sentence to the English sentence it translates even when the two
languages break differently.  The alignment is used to spread Chinese lines
across the same ASR segments as their English counterparts instead of letting
every later line slide one slot down.
"""
from __future__ import annotations

import bisect
import re

# Tokens that survive translation (numbers, callsigns, place names). They anchor
# a Chinese sentence to the English sentence it translates even when the two
# languages break sentences differently.
_ANCHOR_RE = re.compile(r"[A-Za-z]{2,}|\d+(?:\.\d+)?")


def _anchor_tokens(text: str) -> list[str]:
    return _ANCHOR_RE.findall(text.lower())


def _shared_anchors(zh_sents: list[str], en_sents: list[str],
                    max_occ: int = 4) -> list[tuple[int, int]]:
    """Monotonic ``(zh_index, en_index)`` pairs from shared Latin/number tokens.

    Occurrences of a token are paired in order (a translation may drop or repeat
    one), reduced to the furthest English sentence per Chinese sentence, then
    kept only while they stay strictly increasing. Tokens repeated more than
    ``max_occ`` times are ignored as noise.
    """
    ztok: dict[str, list[int]] = {}
    for i, s in enumerate(zh_sents):
        for t in _anchor_tokens(s):
            ztok.setdefault(t, []).append(i)
    etok: dict[str, list[int]] = {}
    for j, s in enumerate(en_sents):
        for t in _anchor_tokens(s):
            etok.setdefault(t, []).append(j)
    # One anchor per Chinese sentence: the furthest English sentence its shared
    # tokens point at. A Chinese sentence that merges two English ones shares a
    # token with each; anchoring it to the later one keeps the following lines
    # from sliding back. Deterministic (tokens sorted) so the build is stable.
    cand: dict[int, int] = {}
    for t in sorted(set(ztok) & set(etok)):
        zl, el = ztok[t], etok[t]
        if len(zl) > max_occ or len(el) > max_occ:
            continue
        for zi, ej in zip(zl, el):
            if zi not in cand or ej > cand[zi]:
                cand[zi] = ej
    anchors: list[tuple[int, int]] = []
    last_e = -1
    for zi in sorted(cand):
        if cand[zi] <= last_e:
            continue
        anchors.append((zi, cand[zi]))
        last_e = cand[zi]
    return anchors


def _sentence_alignment(zh_sents: list[str],
                        en_sents: list[str]) -> list[int] | None:
    """Align each Chinese sentence to one English sentence (monotonic).

    Chinese and English rarely break sentences at the same place. Aligning one
    English sentence per Chinese sentence (and vice versa, via gaps) keeps a
    sentence the translator merged or split with its English counterpart instead
    of pushing every later Chinese line one slot down -- the "收到" pinned to the
    previous line bug. Sentences sharing a token (number, callsign, place name)
    are pinned to each other, so those anchors are never crossed. Returns the
    English index per Chinese sentence, or ``None`` when it cannot be aligned.
    """
    m, n = len(zh_sents), len(en_sents)
    if not m or not n:
        return None
    zl = [max(1, len(s)) for s in zh_sents]
    el = [max(1, len(s)) for s in en_sents]
    az, ae = sum(zl) / m, sum(el) / n
    pinned = dict(_shared_anchors(zh_sents, en_sents))

    def exclam(s: str) -> int:
        return s.count("!") + s.count("?") + s.count("！") + s.count("？")

    def cost(i: int, j: int) -> float:
        c = abs(zl[i] / az - el[j] / ae)
        if exclam(zh_sents[i]) != exclam(en_sents[j]):
            c += 0.4
        c -= 0.5 * len(set(_anchor_tokens(zh_sents[i]))
                       & set(_anchor_tokens(en_sents[j])))
        return c

    gap = 0.9
    inf = float("inf")
    dist = [[inf] * (n + 1) for _ in range(m + 1)]
    back: list[list[tuple[int, int] | None]] = [[None] * (n + 1)
                                                for _ in range(m + 1)]
    dist[0][0] = 0
    for i in range(m + 1):
        for j in range(n + 1):
            cur = dist[i][j]
            if cur == inf:
                continue
            forced = pinned.get(i)
            if i < m and j < n and (forced is None or forced == j):
                c = cur + cost(i, j)
                if c < dist[i + 1][j + 1]:
                    dist[i + 1][j + 1] = c
                    back[i + 1][j + 1] = (i, j)
            if j < n and (forced is None or forced > j):
                c = cur + gap
                if c < dist[i][j + 1]:
                    dist[i][j + 1] = c
                    back[i][j + 1] = (i, j)
            if i < m and forced is None:
                c = cur + gap
                if c < dist[i + 1][j]:
                    dist[i + 1][j] = c
                    back[i + 1][j] = (i, j)
    if dist[m][n] == inf or back[m][n] is None:
        return None
    match: list[int | None] = [None] * m
    i, j = m, n
    while i > 0 or j > 0:
        back_ptr = back[i][j]
        if back_ptr is None:
            break
        pi, pj = back_ptr
        if i > pi and j > pj:
            match[pi] = pj
        i, j = pi, pj
    for r in range(m):
        if match[r] is None:
            prev = next((match[k] for k in range(r - 1, -1, -1)
                         if match[k] is not None), None)
            nxt = next((match[k] for k in range(r + 1, m)
                        if match[k] is not None), None)
            match[r] = prev if prev is not None else (nxt if nxt is not None else 0)
    return [int(x) for x in match]


def _aligned_zh_segments(zh_sents: list[str], en_sents: list[str],
                         seg_of_en: list[int], nsegs: int) -> list[int] | None:
    """ASR segment index per Chinese sentence, or ``None`` if unalignable."""
    if nsegs <= 0 or not zh_sents or not en_sents:
        return None
    match = _sentence_alignment(zh_sents, en_sents)
    if match is None:
        return None
    return [max(0, min(nsegs - 1, seg_of_en[e])) for e in match]


def _proportional_zh_segments(zh_sents: list[str], en_sents: list[str],
                              seg_of_en: list[int], nsegs: int) -> list[int]:
    """Spread Chinese across segments in proportion to their English sentences."""
    m = len(zh_sents)
    if nsegs <= 0 or m == 0:
        return [0] * m
    if not en_sents:
        return [min(nsegs - 1, r * nsegs // m) for r in range(m)]
    en_count = [0] * nsegs
    for e in seg_of_en:
        en_count[e] += 1
    cum = [0]
    for c in en_count:
        cum.append(cum[-1] + c)
    out = []
    for r in range(m):
        target = (r + 0.5) * len(en_sents) / m
        out.append(max(0, min(nsegs - 1, bisect.bisect_right(cum, target) - 1)))
    return out


def _zh_distribution_score(zh_seg: list[int], zh_sents: list[str],
                           en_chars: list[int], tot_zh: int, tot_en: int,
                           anchors: list[tuple[int, int]],
                           seg_of_en: list[int]) -> float:
    """How evenly a Chinese assignment tracks the English content per segment.

    Adds a penalty for a line that carries only one language and for a sentence
    whose shared-token anchor declares a different segment.
    """
    nsegs = len(en_chars)
    zh_chars = [0] * nsegs
    for r, s in enumerate(zh_sents):
        zh_chars[zh_seg[r]] += max(1, len(s))
    score = 0.0
    for i in range(nsegs):
        if en_chars[i] and not zh_chars[i]:
            score += 1.0
        elif zh_chars[i] and not en_chars[i]:
            score += 0.5
        score += abs(zh_chars[i] / tot_zh - en_chars[i] / tot_en)
    for zi, ej in anchors:
        if zh_seg[zi] != seg_of_en[ej]:
            score += 5.0
    return score


def _best_zh_segments(zh_sents: list[str], en_sents: list[str],
                      seg_of_en: list[int], nsegs: int) -> list[int]:
    """Pick the Chinese->segment spread that best matches the English.

    Tries the proportional spread and the word/length sentence alignment, then
    keeps whichever distributes Chinese content across segments most like the
    English (and honours shared-token anchors). This avoids both the drift of a
    pure proportion and the over-eager gaps of a pure length alignment.
    """
    m = len(zh_sents)
    if nsegs <= 0 or m == 0:
        return [0] * m
    prop = _proportional_zh_segments(zh_sents, en_sents, seg_of_en, nsegs)
    candidates = [prop]
    aligned = _aligned_zh_segments(zh_sents, en_sents, seg_of_en, nsegs)
    if aligned is not None and aligned != prop:
        candidates.append(aligned)
    tot_zh = sum(max(1, len(s)) for s in zh_sents) or 1
    en_chars = [0] * nsegs
    for j, e in enumerate(seg_of_en):
        en_chars[e] += max(1, len(en_sents[j]))
    tot_en = sum(en_chars) or 1
    anchors = _shared_anchors(zh_sents, en_sents)
    best = prop
    best_score = None
    for cand in candidates:
        score = _zh_distribution_score(cand, zh_sents, en_chars, tot_zh, tot_en,
                                       anchors, seg_of_en)
        if best_score is None or score < best_score - 1e-9:
            best_score, best = score, cand
    return best

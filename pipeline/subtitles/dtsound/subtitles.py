"""Build the timed-subtitle table spliced into DTSound.as.

One subtitle line is produced per ASR segment, carrying the Chinese and English
text that falls inside that segment so bilingual display stays aligned.  Timing
is exactly the ASR segment start/end -- no per-character inference, which drifts
whenever a sentence is spoken faster or slower than its text length suggests.
"""
from __future__ import annotations

from .alignment import _best_zh_segments
from .as3 import as3_literal, chunk_literals
from .constants import FLD_SEP, REC_SEP, SUB_SEP
from .sentences import split_sentences, split_sentences_en
from .timing import _merged_segment_groups, _sentence_segments


def build_timed_chunks(
    subs: dict[str, str],
    durations: dict[str, float],
    originals: dict[str, str] | None = None,
    min_secs: float = 7.5,
    segments: dict[str, list[dict]] | None = None,
) -> tuple[list[tuple[str, list[tuple[float, float, str, str]]]], str]:
    """Build one subtitle line per ASR segment, timed by the ASR windows.

    Each line carries the Chinese and English text that falls inside that ASR
    segment, so bilingual display stays aligned.  Neighbouring segments that the
    recognizer split out of a single CSV sentence are shown as one line spanning
    both windows.  The chat/stream/subtitle timing is exactly the ASR segment
    start/end -- there is no per-character inference, which drifts whenever a
    sentence is spoken faster or slower than its text length suggests.  Clips
    without ASR data collapse to a single line.
    """
    segments = segments or {}
    originals = originals or {}
    entries: list[tuple[str, list[tuple[float, float, str, str]]]] = []
    for cls, text in sorted(subs.items()):
        if not text:
            continue
        zh_sents = split_sentences(text)
        if not zh_sents:
            continue
        dur = float(durations.get(cls, 0.0))
        en = str(originals.get(cls) or "").strip()
        en_sents = split_sentences_en(en) if en else []
        segs = [
            s
            for s in (segments.get(cls) or [])
            if float(s.get("end") or 0.0) > float(s.get("start") or 0.0)
        ]
        pairs: list[tuple[float, float, str, str]] = []
        if segs:
            # One subtitle line per ASR segment, using the segment's own start/end
            # verbatim -- exactly like a video subtitle track.  English sentences
            # are attached to the segment whose transcribed words they match;
            # Chinese follows sentence order.  No character-count interpolation is
            # used, so a fast or slow delivery no longer drifts out of sync.
            seg_of_en = _sentence_segments(en_sents, segs)
            if seg_of_en is None:
                seg_of_en = [
                    min(len(segs) - 1, i * len(segs) // len(en_sents))
                    for i in range(len(en_sents))
                ] if en_sents else []
            en_groups: list[list[str]] = [[] for _ in segs]
            for i, s in enumerate(en_sents):
                en_groups[seg_of_en[i]].append(s)
            zh_groups: list[list[str]] = [[] for _ in segs]
            # Spread Chinese across the segments so its content lands on the
            # same lines as its English counterpart. This keeps a merged/split
            # sentence with its own line instead of shifting every later line
            # (the "收到" pinned to the previous line bug).
            zh_seg = _best_zh_segments(zh_sents, en_sents, seg_of_en, len(segs))
            for r, s in enumerate(zh_sents):
                zh_groups[zh_seg[r]].append(s)
            for lo, hi in _merged_segment_groups(en_sents, segs):
                st = round(float(segs[lo].get("start") or 0.0), 2)
                en_t = round(float(segs[hi].get("end") or 0.0), 2)
                zt = "".join("".join(zh_groups[k]) for k in range(lo, hi + 1))
                et = " ".join(" ".join(en_groups[k])
                              for k in range(lo, hi + 1)).strip()
                if not et and not en:
                    # No translation source at all: fall back to the recognizer's
                    # own English so the line is not silently dropped.
                    et = " ".join(str(segs[k].get("text") or "").strip()
                                  for k in range(lo, hi + 1)).strip()
                if not zt and not et:
                    continue
                pairs.append((st, en_t, zt, et))
        else:
            # No ASR segment for this clip: fall back to a single line spanning it.
            pairs.append((0.0, round(dur, 2) if dur > 0 else 0.0,
                          "".join(zh_sents), " ".join(en_sents)))
        if pairs:
            entries.append((cls, pairs))

    recs: list[str] = []
    for cls, timed in entries:
        rec = cls + FLD_SEP + SUB_SEP.join(
            "%.2f%s%.2f%s%s%s%s" % (st, FLD_SEP, en, FLD_SEP, tx, FLD_SEP, tx_en)
            for st, en, tx, tx_en in timed
        ) + REC_SEP
        recs.append(as3_literal(rec))
    return entries, chunk_literals(recs, 200)

"""Fuzzy label matching for OCR'd form text.

The problem this solves: PaddleOCR's Tamil model mangles label text. A label
printed as `கணவர் பெயர்` may come back as `கணவா பெயா` or `கணவர்பெயர்`.
Exact matching loses the field entirely.

Why not `partial_ratio`
-----------------------
The obvious approach -- fuzzy substring search for each label -- is actively
wrong here. `partial_ratio(label, text)` scores the *best matching substring
of the label*, so `மற்றவை பெயர்` scores ~100 against any text containing
`பெயர்`. Every specific label contains the generic `பெயர்` (name) label, so
they all match everything and the longest one wins by accident.

The approach that works
-----------------------
These forms are strictly `LABEL : VALUE`, so we anchor on the separator:

1. Split the line on colon-like characters.
2. The text before a separator ends with a label; the text after it begins
   with a value. A middle segment is `value_of_previous + label_of_next`, so
   we find where the next label starts by scoring **suffixes** of that
   segment.
3. Score with full `fuzz.ratio`, which is length-sensitive: matching
   `பெயர்` (5 chars) against `மற்றவை பெயர்` (12) scores ~59, while
   `பெயர்` against `பெயர்` scores 100. The right label now wins on merit.

This also splits a line carrying two fields
(`வயது : 34  பாலினம் : பெண்`) into both of them.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from rapidfuzz import fuzz

# Characters OCR substitutes for the ':' separator.
_SEP_CHARS = ":;：﹕∶|"
_SEP_SPLIT_RE = re.compile(f"[{re.escape(_SEP_CHARS)}]")
_LEADING_JUNK_RE = re.compile(r"^[\s\-–—.,;:]+")
_TRAILING_JUNK_RE = re.compile(r"[\s\-–—_.,;:\"'\u201c\u201d\u2018\u2019]+")
_WS_RE = re.compile(r"\s+")

# A label is short; no need to test suffixes longer than this.
_MAX_LABEL_CHARS = 24


# --- Tamil vowel-sign repair ----------------------------------------------
# Two dependent vowel signs cannot legally follow one another in Tamil, but
# PaddleOCR emits such pairs regularly -- it recognises the visually
# left-placed part of a sign *and* the composed sign, giving e.g.
# `தந்தெையின்` (ெ + ை) where the form reads `தந்தையின்` (ை alone).
# Left uncorrected this costs real accuracy: it degraded the label match for
# `தந்தையின் பெயர்` from 100 to 97 and lost the field.
_TAMIL_SIGNS = frozenset("ாிீுூெேை"
                         "ொோௌௗ")

# Pairs that are a genuine decomposition and must be *combined*, not dropped.
_TAMIL_COMPOSE = {
    ("ெ", "ா"): "ொ",  # e  + aa -> o
    ("ே", "ா"): "ோ",  # ee + aa -> oo
    ("ெ", "ௗ"): "ௌ",  # e  + au length mark -> au
}


def fix_tamil_vowel_signs(text: str) -> str:
    """Repair invalid runs of consecutive Tamil vowel signs.

    Genuine decompositions are composed; anything else keeps the *last*
    sign, which is empirically the correct one (the spurious sign is the
    left-placed glyph component the model emitted first).
    """
    if not text:
        return text
    out: list[str] = []
    for ch in text:
        if out and ch in _TAMIL_SIGNS and out[-1] in _TAMIL_SIGNS:
            composed = _TAMIL_COMPOSE.get((out[-1], ch))
            out[-1] = composed if composed else ch
            continue
        out.append(ch)
    return "".join(out)


def normalize(text: str) -> str:
    """NFC-normalise, repair Tamil vowel signs, and collapse whitespace.

    NFC matters for Tamil: the same visual grapheme can arrive composed or
    decomposed depending on the model's dictionary, and the two forms are
    not byte-equal.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = fix_tamil_vowel_signs(text)
    return _WS_RE.sub(" ", text).strip()


def strip_value(text: str) -> str:
    """Clean an extracted field value."""
    text = normalize(text)
    text = _LEADING_JUNK_RE.sub("", text)
    text = _TRAILING_JUNK_RE.sub("", text)
    return text.strip()


@dataclass
class LabelMatch:
    key: str
    """Logical field key this label maps to."""
    label: str
    """The canonical label variant that matched."""
    score: float
    start: int
    end: int
    """Character span of the label within the source line."""


# ---------------------------------------------------------------------------
# Core scoring
# ---------------------------------------------------------------------------


def _score_label(candidate: str, label_map: dict[str, list[str]]) -> tuple[str, str, float]:
    """Best (key, variant, score) for a string believed to *be* a label."""
    candidate = normalize(candidate)
    if not candidate:
        return "", "", 0.0

    best_key, best_variant, best_score = "", "", 0.0
    for key, variants in label_map.items():
        for variant in variants:
            if not variant:
                continue
            score = fuzz.ratio(variant, candidate)
            # Tie-break toward the longer variant: if two labels score the
            # same, the more specific one is the better explanation.
            if (score, len(variant)) > (best_score, len(best_variant)):
                best_key, best_variant, best_score = key, variant, score
    return best_key, best_variant, best_score


def _match_trailing_label(
    segment: str, label_map: dict[str, list[str]], threshold: float
) -> tuple[str, str, float, int]:
    """Find a label occupying the *end* of `segment`.

    Returns (key, variant, score, start_index). `start_index` is where the
    label begins, so the caller can take everything before it as the value.
    """
    segment = segment.rstrip()
    if not segment:
        return "", "", 0.0, -1

    best = ("", "", 0.0, -1)
    limit = min(len(segment), _MAX_LABEL_CHARS)
    # Try every suffix, shortest first, and rank by **how much of the segment
    # the label explains**, not by raw score.
    #
    # Ranking by score alone is wrong here: `பெயர்` matches its own 5
    # characters perfectly (100) while `தந்தையின் பெயர்` matches a slightly
    # OCR-degraded 15-character segment at 97 -- and the short generic label
    # would win, stealing the field from the specific one. Coverage first,
    # score only as a tie-break, with `threshold` filtering out noise.
    for length in range(1, limit + 1):
        start = len(segment) - length
        suffix = segment[start:]
        key, variant, score = _score_label(suffix, label_map)
        if score >= threshold and (len(variant), score) > (len(best[1]), best[2]):
            best = (key, variant, score, start)
    return best


def find_label(
    text: str,
    variants: list[str],
    key: str,
    threshold: float,
) -> LabelMatch | None:
    """Locate a single label within `text`. Used by templates for probing."""
    text = normalize(text)
    if not text:
        return None

    best: LabelMatch | None = None
    for variant in variants:
        if not variant:
            continue
        span = len(variant)
        # Slide a window sized like the label; full ratio keeps it
        # length-sensitive, unlike partial_ratio.
        for start in range(0, max(1, len(text) - span + 2)):
            for width in {span, span + 1, span + 2, max(1, span - 1)}:
                window = text[start : start + width]
                if not window.strip():
                    continue
                score = fuzz.ratio(variant, window)
                if score >= threshold and (best is None or score > best.score):
                    best = LabelMatch(
                        key=key,
                        label=variant,
                        score=score,
                        start=start,
                        end=start + len(window),
                    )
    return best


# ---------------------------------------------------------------------------
# Line segmentation
# ---------------------------------------------------------------------------


def segment_labels(
    text: str,
    label_map: dict[str, list[str]],
    threshold: float,
    priority: list[str] | None = None,
) -> list[tuple[LabelMatch, str]]:
    """Split a `LABEL : VALUE [LABEL : VALUE ...]` line into its pairs.

    With ``n`` separators the line decomposes into ``n + 1`` segments::

        "வயது : 34 பாலினம் : பெண்"
         └─ seg0 ─┘└── seg1 ──┘└ seg2 ┘
            LABEL   VALUE+LABEL   VALUE

    So ``seg[0]`` is a label, ``seg[n]`` is a value, and every segment in
    between is *the previous field's value followed by the next field's
    label*. Finding where that boundary falls is a trailing-label search.

    `priority` only breaks exact score ties -- it never overrides a
    better-scoring match.
    """
    text = normalize(text)
    if not text:
        return []

    priority = priority or []

    sep_positions = [m.start() for m in _SEP_SPLIT_RE.finditer(text)]
    if not sep_positions:
        return []

    # Cut the line into segments, remembering where each starts.
    segments: list[tuple[int, str]] = []
    cursor = 0
    for pos in sep_positions:
        segments.append((cursor, text[cursor:pos]))
        cursor = pos + 1
    segments.append((cursor, text[cursor:]))

    n = len(sep_positions)
    labels: list[LabelMatch | None] = []
    values: list[str] = []

    # seg[0] is pure label (possibly with leading OCR noise).
    head_start, head = segments[0]
    key, variant, score, offset = _match_trailing_label(head, label_map, threshold)
    if not key:
        key, variant, score = _score_label(head, label_map)
        offset = 0
    labels.append(
        LabelMatch(key=key, label=variant, score=score,
                   start=head_start + max(offset, 0), end=head_start + len(head))
        if key and score >= threshold
        else None
    )

    # Middle segments: value of the previous field, then the next label.
    for i in range(1, n):
        seg_start, segment = segments[i]
        key, variant, score, offset = _match_trailing_label(segment, label_map, threshold)
        if key and offset >= 0:
            values.append(segment[:offset])
            labels.append(
                LabelMatch(key=key, label=variant, score=score,
                           start=seg_start + offset, end=seg_start + len(segment))
            )
        else:
            # No recognisable label here -- treat the whole segment as value
            # and drop the field this separator would have introduced.
            values.append(segment)
            labels.append(None)

    # The final segment is pure value.
    values.append(segments[n][1])

    pairs: list[tuple[LabelMatch, str]] = []
    for label, value in zip(labels, values):
        if label is not None:
            pairs.append((label, strip_value(value)))

    # Keep the best occurrence per key; `priority` breaks exact ties only.
    best_by_key: dict[str, tuple[LabelMatch, str]] = {}
    for match, value in pairs:
        existing = best_by_key.get(match.key)
        if existing is None:
            best_by_key[match.key] = (match, value)
            continue
        if (match.score, 1 if match.key in priority else 0) > (
            existing[0].score,
            1 if existing[0].key in priority else 0,
        ):
            best_by_key[match.key] = (match, value)

    return sorted(best_by_key.values(), key=lambda pair: pair[0].start)


# ---------------------------------------------------------------------------
# Value cleaning
# ---------------------------------------------------------------------------


def extract_digits(text: str) -> str:
    """Digits only, with common OCR letter-for-digit confusions repaired."""
    if not text:
        return ""
    fixed = (
        text.replace("O", "0").replace("o", "0")
        .replace("I", "1").replace("l", "1").replace("|", "1")
        .replace("S", "5").replace("B", "8")
    )
    return "".join(ch for ch in fixed if ch.isdigit())


def clean_identifier(text: str) -> str:
    """Uppercase alphanumerics only -- for EPIC-style identifiers."""
    if not text:
        return ""
    return "".join(ch for ch in text.upper() if ch.isalnum())


def best_enum_match(
    value: str, options: dict[str, str], threshold: float = 70.0
) -> str | None:
    """Map an OCR'd value onto a canonical enum member.

    `options` maps canonical output -> source-language token.
    """
    value = normalize(value)
    if not value:
        return None

    # Exact containment first. Short Tamil tokens fuzzy-match each other far
    # too easily (ஆண் vs பெண் differ by one grapheme), so fuzzy scoring is
    # only a fallback.
    for canonical, token in options.items():
        if token and token in value:
            return canonical

    best_key, best_score = None, 0.0
    for canonical, token in options.items():
        score = fuzz.ratio(token, value)
        if score > best_score:
            best_key, best_score = canonical, score
    return best_key if best_score >= threshold else None

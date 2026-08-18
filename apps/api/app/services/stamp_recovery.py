"""Recovering the age the DELETED stamp cost, by agreement across re-reads.

On a struck-off card the stamp crosses the age line and the recognizer drops a
digit: `59` is returned as `5`, which falls under the electoral minimum and is
discarded, so the elector ends up with no age at all.

Re-reading a narrower crop usually recovers the digit. Which width works does
not follow a rule -- on three real cards, fractions 0.45 and 0.55 recovered every
age while 0.50, 0.60 and 0.65 recovered none. That is the recognizer's internal
resizing, so picking the winning fraction would be fitting to three samples and
would not survive a change of DPI or model build.

Instead every variant is read, readings that cannot be an age are dropped, and a
value is returned only if the survivors agree. On those cards the implausible
readings are exactly the damaged ones and the survivors are unanimous.

Erasing the stamp ink was tried first and rejected: it recovered one age of three,
because a stroke touching a glyph cannot be removed without taking glyph with it.

**Known limit.** Agreement among plausible readings is not proof of correctness.
Two variants could agree on a wrong-but-plausible age and nothing here would
notice. What it rules out is trusting a single lucky read -- the failure mode that
would otherwise be silent, since a damaged age line comes back at 0.94+
confidence.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import cv2
import numpy as np

from ..templates.text_utils import extract_digits

# Electoral bounds. A reading outside them is damage, not an age.
MIN_AGE = 18
MAX_AGE = 120

# Widths to re-read, as fractions of cell width. A spread rather than a choice:
# no single one of these is believed to be correct.
_CROP_FRACTIONS: tuple[float, ...] = (0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 1.00)

# Pages render at their own native resolution, which for these scans is ~143 dpi,
# and at that size the recognizer loses digits it can read when the crop is
# enlarged. On the real roll, enlarging recovered 21 of 48 otherwise-lost ages
# against 5 without it. Enlarging first because it succeeds more often, which
# ends the loop sooner; it is not trusted more, since agreement still decides.
_UPSCALES: tuple[float, ...] = (2.0, 1.0)

# How many plausible readings must agree. Two is the smallest number that stops a
# single lucky read from being trusted.
_MIN_AGREEING = 2

_AGE_LABEL = "வயது"

OcrReader = Callable[[np.ndarray], Sequence[str]]
"""Reads a crop and returns its text lines. Injected so recovery is testable
without loading a recognition model."""


def _age_in(lines: Sequence[str]) -> int | None:
    for text in lines:
        if _AGE_LABEL not in text:
            continue
        digits = extract_digits(text)
        if not digits:
            return None
        try:
            value = int(digits)
        except ValueError:
            return None
        return value if MIN_AGE <= value <= MAX_AGE else None
    return None


def recover_age(cell: np.ndarray, read: OcrReader) -> int | None:
    """The elector's age, or None when the re-reads do not agree on one.

    None means "not recovered", never "no age". The caller should leave the field
    unreadable rather than store a value this could not confirm: a silently wrong
    age is worse than a missing one.
    """
    width = cell.shape[1]
    plausible: list[int] = []

    for scale, fraction in ((s, f) for s in _UPSCALES for f in _CROP_FRACTIONS):
        cut = int(width * fraction)
        if cut < 40:
            continue
        crop = cell if cut >= width else cell[:, :cut]
        if scale != 1.0:
            crop = cv2.resize(
                crop, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC
            )
        try:
            age = _age_in(read(crop))
        except Exception:
            continue
        if age is None:
            continue
        plausible.append(age)
        # Enough agreement already: stop paying for re-reads. Recovery runs per
        # stamped cell, so the reads it does not do are the bulk of its cost.
        if len(plausible) >= _MIN_AGREEING and len(set(plausible)) == 1:
            return age

    if len(plausible) < _MIN_AGREEING:
        return None
    if len(set(plausible)) != 1:
        return None
    return plausible[0]

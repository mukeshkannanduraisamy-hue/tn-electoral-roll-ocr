"""Detecting fields the DELETED stamp ran through.

The stamp crosses the lower-left of every struck-off card, landing on the age,
house-number and relation-name lines. Two of those three corruptions are
plausible and pass every existing check:

    வீட்டு எண் : 2-2   ->   வீட்டு எண் : 22      (hyphen eaten; a valid house no.)
    தந்தை பெயர்: காளியப்பன்  ->  ...கூளியீப்பன்   (valid-looking Tamil)

The age corruption is *not* silent -- a lost digit leaves a single digit below
MIN_AGE, so the range check catches it and the age is coerced to unknown. That
is data loss rather than a wrong value, but it is still loss worth recovering.

Confidence cannot drive any of this: the damaged age lines below came back at
0.936-0.962, higher than the 0.710-0.837 the deletion signal itself scores.

Strings are verbatim PaddleOCR output for TAM-16 page 4 (serials 13, 14, 20
stamped; 17, 19, 23 clean).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.templates.field_integrity import (  # noqa: E402
    age_gender_line_is_intact,
    house_number_is_intact,
)

STAMP_DAMAGED_AGE_LINES = [
    "வயது : 5ஆபீலினம் : ஆண்",      # serial 13, truth "வயது : 59 பாலினம் : ஆண்"
    "வயது : 4ூபிலினம் : பெண்",      # serial 14, truth 44
    "வயது : 3யீலினம் : ஆண்",        # serial 20, truth 30
]

INTACT_AGE_LINES = [
    "வயது : 22 பாலினம் : பெண்",     # serial 17
    "வயது : 53 பாலினம் : ஆண்",      # serial 19
    "வயது : 38 பாலினம் : ஆண்",      # serial 23
]


@pytest.mark.parametrize("line", STAMP_DAMAGED_AGE_LINES)
def test_stamp_damaged_age_line_is_rejected(line):
    """A digit running straight into a Tamil letter means the stamp hit it."""
    assert age_gender_line_is_intact(line) is False


@pytest.mark.parametrize("line", INTACT_AGE_LINES)
def test_clean_age_line_is_accepted(line):
    assert age_gender_line_is_intact(line) is True


def test_age_line_missing_the_gender_label_is_rejected():
    """The stamp can swallow the label whole, not just merge it."""
    assert age_gender_line_is_intact("வயது : 59") is False


def test_age_line_with_no_digits_is_rejected():
    assert age_gender_line_is_intact("வயது :  பாலினம் : ஆண்") is False


def test_house_number_keeping_its_separator_is_intact():
    for value in ("2-2", "2/19", "2-22A", "1"):
        assert house_number_is_intact(value) is True, value


def test_house_number_that_lost_its_separator_is_flagged():
    """`2-2` read as `22` is the silent case: plausible, and wrong.

    A bare multi-digit run cannot be distinguished from a genuine house number
    by looking at it alone, so this is reported as *not verifiable* and left for
    the stamp geometry to arbitrate -- only cells the stamp actually crossed get
    re-read.
    """
    assert house_number_is_intact("22") is False
    assert house_number_is_intact("224") is False

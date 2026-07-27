"""Parser tests using OCR output captured from real electoral-roll pages.

These strings are verbatim PaddleOCR output from
`2026-EROLLGEN-S22-57-SIR-FinalRoll-Revision1-TAM-10-WI/10_10.pdf`, so the
tests exercise exactly the text the parser sees in production -- including
its quirks (missing space before the colon, trailing hyphens, two fields
sharing one line).

No PaddleOCR import here: these run in milliseconds and are safe for CI.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.templates.electoral_roll_ta import (  # noqa: E402
    GENDER_OPTIONS,
    LABELS,
    RELATION_KEYS,
)
from app.templates.text_utils import (  # noqa: E402
    best_enum_match,
    clean_identifier,
    extract_digits,
    fix_tamil_vowel_signs,
    segment_labels,
    strip_value,
)

THRESHOLD = 62


def parse(text: str) -> dict[str, str]:
    """Convenience: run the real segmenter and flatten to {key: value}."""
    return {
        match.key: value
        for match, value in segment_labels(
            text, LABELS, threshold=THRESHOLD, priority=RELATION_KEYS
        )
    }


# ---------------------------------------------------------------------------
# The bug that motivated this file: `பெயர்` is a substring of every relation
# label, so a naive fuzzy match assigns the name to the relation field.
# ---------------------------------------------------------------------------


def test_plain_name_is_not_stolen_by_relation_labels():
    result = parse("பெயர் : சுசீலா -")
    assert result.get("name") == "சுசீலா"
    assert "relation_husband" not in result
    assert "relation_other" not in result


def test_husband_relation_beats_generic_name_label():
    result = parse("கணவர் பெயர்: சண்முகம் -")
    assert result.get("relation_husband") == "சண்முகம்"
    assert "name" not in result


def test_father_relation_is_distinct_from_husband():
    result = parse("தந்தையின் பெயர்: முனிசாமி -")
    assert result.get("relation_father") == "முனிசாமி"
    assert "relation_husband" not in result


def test_mother_relation():
    result = parse("தாயின் பெயர் : கமலா")
    assert result.get("relation_mother") == "கமலா"


# ---------------------------------------------------------------------------
# Two fields sharing one line
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line,age,gender_token",
    [
        ("வயது : 34 பாலினம் : பெண்", "34", "பெண்"),
        ("வயது : 87 பாலினம் : ஆண்", "87", "ஆண்"),
        ("வயது : 20 பாலினம் : ஆண்", "20", "ஆண்"),
    ],
)
def test_age_and_gender_split_from_one_line(line, age, gender_token):
    result = parse(line)
    assert result.get("age") == age
    assert result.get("gender") == gender_token


def test_gender_alone_on_its_own_line():
    assert parse("பாலினம் : பெண்").get("gender") == "பெண்"


# ---------------------------------------------------------------------------
# Other fields
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line,expected",
    [
        ("வீட்டு எண் : 5-177", "5-177"),
        ("வீட்டு எண் : 5/177", "5/177"),
        ("வீட்டு எண் : 5-179-1", "5-179-1"),
        ("வீட்டு எண்: 5/179-3", "5/179-3"),
    ],
)
def test_house_number_keeps_separators(line, expected):
    """House numbers contain '-' and '/', which must survive value cleaning."""
    assert parse(line).get("house_number") == expected


def test_missing_space_before_colon():
    assert parse("பெயர்: காமாட்சி").get("name") == "காமாட்சி"


def test_line_without_separator_yields_nothing():
    assert parse("Photo is available") == {}


def test_empty_line():
    assert parse("") == {}


# ---------------------------------------------------------------------------
# Value helpers
# ---------------------------------------------------------------------------


def test_strip_value_removes_trailing_hyphen():
    assert strip_value(" சுசீலா - ") == "சுசீலா"


def test_extract_digits_repairs_ocr_confusions():
    assert extract_digits("O34") == "034"
    assert extract_digits("l8") == "18"


def test_clean_identifier():
    assert clean_identifier("zht 0308742") == "ZHT0308742"
    assert clean_identifier("BVN-1077692") == "BVN1077692"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("பெண்", "Female"),
        ("ஆண்", "Male"),
        ("மற்றவை", "Other"),
        ("பெண", "Female"),  # missing pulli
    ],
)
def test_gender_enum_mapping(raw, expected):
    assert best_enum_match(raw, GENDER_OPTIONS) == expected


def test_gender_enum_rejects_noise():
    assert best_enum_match("xyzzy", GENDER_OPTIONS) is None


# ---------------------------------------------------------------------------
# Tamil vowel-sign repair
#
# PaddleOCR emits the left-placed glyph component *and* the composed sign,
# producing consecutive vowel signs that are invalid Tamil. Verbatim cases
# observed on page 10_10.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "broken,fixed",
    [
        ("தந்தெையின்", "தந்தையின்"),  # ெ + ை -> ை
        ("சுரெேஷ்", "சுரேஷ்"),  # ெ + ே -> ே
        ("இரொாஜெந்திரன்", "இராஜெந்திரன்"),  # ொ + ா -> ா
    ],
)
def test_fix_tamil_vowel_signs(broken, fixed):
    assert fix_tamil_vowel_signs(broken) == fixed


def test_vowel_sign_repair_composes_genuine_decompositions():
    """ெ + ா is a real decomposition of ொ and must combine, not drop."""
    assert fix_tamil_vowel_signs("ரொ") == "ரொ"
    assert fix_tamil_vowel_signs("ரோ") == "ரோ"


def test_vowel_sign_repair_leaves_valid_text_untouched():
    for text in ["சுசீலா", "இராகவன்", "வள்ளியம்மாள்", "பாலினம்", "5-179-1"]:
        assert fix_tamil_vowel_signs(text) == text


# ---------------------------------------------------------------------------
# Regression: a slightly OCR-degraded specific label must still beat the
# generic `பெயர்` label it contains. This is the exact line from record 205
# that produced the only failure on page 10_10.
# ---------------------------------------------------------------------------


def test_degraded_father_label_still_beats_generic_name():
    result = parse("தந்தெையின் பெயர்: இராஜெந்திரன் -")
    assert result.get("relation_father") == "இராஜெந்திரன்"
    assert "name" not in result


def test_degraded_husband_label_still_beats_generic_name():
    result = parse("கணவா பெயர் : சண்முகம்")
    assert result.get("relation_husband") == "சண்முகம்"
    assert "name" not in result

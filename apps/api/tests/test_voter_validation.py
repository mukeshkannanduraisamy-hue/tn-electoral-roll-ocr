"""Validation rules for the curated voter table.

The curated table exists precisely so these rules can be strict: OCR output
is accepted with its flaws, but anything promoted here has been checked.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app.schemas.voters import (  # noqa: E402
    VoterCreate,
    VoterUpdate,
    normalise_epic,
)

VALID = {
    "epic": "ZHT0308742",
    "name": "சுசீலா",
    "serial": 181,
    "relation_type": "Husband",
    "relation_name": "சண்முகம்",
    "house_number": "5-177",
    "age": 34,
    "gender": "Female",
    "part_number": "10",
}


def test_valid_record_accepted():
    v = VoterCreate(**VALID)
    assert v.epic == "ZHT0308742"
    assert v.name == "சுசீலா"


# ---------------------------------------------------------------------------
# EPIC
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("zht0308742", "ZHT0308742"),
        ("ZHT 0308742", "ZHT0308742"),
        ("ZHT-0308742", "ZHT0308742"),
        (" bvn1077692 ", "BVN1077692"),
    ],
)
def test_epic_normalised(raw, expected):
    """OCR leaves stray spaces and dashes; those are formatting, not identity."""
    assert VoterCreate(**{**VALID, "epic": raw}).epic == expected


@pytest.mark.parametrize(
    "bad",
    ["", "   ", "ZHT", "1234567", "TOOMANYLETTERS123456", "ZH12345", "!!!"],
)
def test_malformed_epic_rejected(bad):
    with pytest.raises(ValidationError):
        VoterCreate(**{**VALID, "epic": bad})


def test_normalise_epic_helper():
    assert normalise_epic("zht 030-8742") == "ZHT0308742"
    assert normalise_epic("") == ""
    assert normalise_epic(None) == ""


# ---------------------------------------------------------------------------
# Age
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("age", [18, 34, 87, 120])
def test_plausible_ages_accepted(age):
    assert VoterCreate(**{**VALID, "age": age}).age == age


@pytest.mark.parametrize("age", [0, 5, 17, 121, 999, -3])
def test_implausible_ages_become_unknown(age):
    """An impossible age is recorded as unknown, not rejected.

    This validator runs on read as well as write, and the promoted corpus
    genuinely contains ages OCR mis-read as 0. Raising would turn one bad row
    into a 400 for the whole list endpoint, so the age is dropped instead --
    a missing age is honest, a wrong one is not.
    """
    assert VoterCreate(**{**VALID, "age": age}).age is None


def test_a_non_numeric_age_becomes_unknown():
    """OCR can emit anything; a value that is not a number is not an age."""
    assert VoterCreate(**{**VALID, "age": "abc"}).age is None


def test_age_may_be_absent():
    """OCR does sometimes fail to read an age; that is missing, not invalid."""
    assert VoterCreate(**{**VALID, "age": None}).age is None


# ---------------------------------------------------------------------------
# Enums and coupled fields
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("gender", ["Male", "Female", "Other", ""])
def test_valid_genders(gender):
    assert VoterCreate(**{**VALID, "gender": gender}).gender == gender


@pytest.mark.parametrize("gender", ["male", "F", "Unknown", "ஆண்"])
def test_invalid_genders_rejected(gender):
    with pytest.raises(ValidationError):
        VoterCreate(**{**VALID, "gender": gender})


def test_relation_name_without_type_rejected():
    """A relation name with no type reads as complete in an export but is not."""
    with pytest.raises(ValidationError):
        VoterCreate(**{**VALID, "relation_name": "சண்முகம்", "relation_type": ""})


def test_relation_type_without_name_allowed():
    """The reverse is fine: the type is known, the name was not readable."""
    v = VoterCreate(**{**VALID, "relation_name": "", "relation_type": "Father"})
    assert v.relation_type == "Father"


def test_empty_name_rejected():
    with pytest.raises(ValidationError):
        VoterCreate(**{**VALID, "name": ""})


# ---------------------------------------------------------------------------
# House numbers -- the field a bad cleanup regex once corrupted
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("house", ["5-177", "5/177", "5-179-1", "4/420-2", "4-423-2"])
def test_house_number_separators_preserved(house):
    assert VoterCreate(**{**VALID, "house_number": house}).house_number == house


# ---------------------------------------------------------------------------
# PATCH semantics
# ---------------------------------------------------------------------------


def test_update_allows_partial():
    u = VoterUpdate(age=44)
    assert u.model_dump(exclude_unset=True) == {"age": 44}


def test_update_still_validates():
    """An edit is still checked -- a malformed EPIC is refused outright."""
    with pytest.raises(ValidationError):
        VoterUpdate(epic="nonsense")


def test_update_drops_an_implausible_age_rather_than_refusing():
    """Same coercion as create: the age is dropped, the edit still applies.

    Worth knowing when reviewing an edit screen: typing 3 does not raise, it
    silently clears the age. That follows from one shared validator serving
    create, read and update.
    """
    assert VoterUpdate(age=3).age is None


def test_update_can_clear_optional_age():
    assert VoterUpdate(age=None).age is None


def test_whitespace_stripped():
    v = VoterCreate(**{**VALID, "name": "  சுசீலா  ", "house_number": " 5-177 "})
    assert v.name == "சுசீலா"
    assert v.house_number == "5-177"

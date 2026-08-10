"""Combining the two independent signals that mark an elector struck off.

A Special Intensive Revision roll says it twice: a reason-code letter prefixing
the serial, and a diagonal DELETED stamp across the card. On TAM-16 page 4 the
two agreed on all 15 cards checked, which is what makes them useful as a
cross-check -- so the verdict records *which* fired rather than collapsing both
into one boolean. Either alone is sufficient to strike the elector off.

They are not equally legible. The prefix is the lowest-confidence line on a
stamped card (0.710-0.837, against 0.90+ for everything else), so a confidence
gate would discard it. The stamp is never returned by OCR at all.

`S2` on serial 25 is the one code whose meaning is unknown -- every other stamped
card carries a single letter. It is recorded verbatim and treated as deleted,
without being mapped to a meaning we cannot verify.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.templates.deletion_signals import (  # noqa: E402
    assess_deletion,
    parse_reason_code,
)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("S        13", "S"),
        ("S 20", "S"),
        ("E 7", "E"),
        ("R 41", "R"),
        ("M 3", "M"),
        ("Q 88", "Q"),
        ("W 12", "W"),
        ("S2       25", "S2"),      # serial 25, meaning unknown
        ("17", None),
        ("  24  ", None),
        ("", None),
    ],
)
def test_reason_code_is_read_off_the_serial_box(text, expected):
    assert parse_reason_code(text) == expected


def test_lowercase_code_is_accepted():
    """OCR returns a lone letter unreliably; case is not evidence."""
    assert parse_reason_code("s 13") == "S"


def test_the_letter_is_the_reason_the_elector_was_removed():
    """Per the legend printed on the roll's own last page:

        E- Expired, S- Shifted, R-Repeated, M - Missing, Q- Disqualified
    """
    verdict = assess_deletion(reason_code="S", stamp_found=False)
    assert verdict.is_deleted is True
    assert "Shifted" in verdict.reason
    assert verdict.signals == ("reason_code",)


@pytest.mark.parametrize(
    "code,meaning",
    [("E", "Expired"), ("S", "Shifted"), ("R", "Repeated"),
     ("M", "Missing"), ("Q", "Disqualified")],
)
def test_every_documented_code_is_mapped(code, meaning):
    assert meaning in assess_deletion(reason_code=code, stamp_found=False).reason


def test_a_trailing_digit_keeps_the_reason_and_notes_the_supplement():
    """`S2` is still a shift; the digit says which supplement recorded it.

    TAM-16 declares 226 deletions in supplement 1 and 7 in supplement 2, and
    extraction found exactly 226 `S` and 7 `S2` -- so the digit tracks the
    supplement while the letter keeps its documented meaning.
    """
    verdict = assess_deletion(reason_code="S2", stamp_found=False)
    assert verdict.is_deleted is True
    assert "Shifted" in verdict.reason
    assert "2" in verdict.reason


def test_a_letter_the_legend_does_not_list_is_not_given_a_meaning():
    """`W` was in an earlier map and is not on the roll's legend."""
    verdict = assess_deletion(reason_code="W", stamp_found=False)
    assert verdict.is_deleted is True
    assert verdict.reason.startswith("W")
    for invented in ("Withdrawn", "Shifted", "Expired"):
        assert invented not in verdict.reason


def test_stamp_alone_is_enough():
    verdict = assess_deletion(reason_code=None, stamp_found=True)
    assert verdict.is_deleted is True
    assert verdict.signals == ("stamp",)


def test_both_signals_are_recorded_so_disagreements_stay_auditable():
    verdict = assess_deletion(reason_code="S", stamp_found=True)
    assert verdict.is_deleted is True
    assert verdict.signals == ("reason_code", "stamp")


def test_neither_signal_means_an_actively_evaluated_live_elector():
    """Must be distinguishable from "never looked at" -- see is_deleted below."""
    verdict = assess_deletion(reason_code=None, stamp_found=False)
    assert verdict.is_deleted is False
    assert verdict.signals == ()


def test_deletions_page_does_not_override_per_cell_evidence():
    """Page 4 of TAM-16 is mixed: 15 of 30 stamped.

    A page-level flag that wins would strike off every live elector sharing the
    page with a deleted one.
    """
    verdict = assess_deletion(
        reason_code=None, stamp_found=False, on_deletions_page=True
    )
    assert verdict.is_deleted is False


def test_deletions_page_is_still_recorded_when_a_cell_agrees():
    verdict = assess_deletion(
        reason_code="S", stamp_found=True, on_deletions_page=True
    )
    assert verdict.is_deleted is True
    assert "deletions_page" in verdict.signals


def test_verdict_renders_the_stored_flag_as_an_explicit_yes_or_no():
    """`""` currently means both "active" and "never evaluated"."""
    assert assess_deletion(reason_code="S", stamp_found=False).flag == "Yes"
    assert assess_deletion(reason_code=None, stamp_found=False).flag == "No"

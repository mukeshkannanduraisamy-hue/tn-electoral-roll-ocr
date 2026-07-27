"""Tests for cross-corpus spelling consensus.

The cases below are the real conflicting spellings observed on page 10_10 of
the sample corpus. Two of them are deliberately *unresolvable* -- the point
of this module is that a bare majority is not good enough when the data is
people's names.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.schemas.core import FieldValue, IssueCode, Page, Record  # noqa: E402
from app.services.consensus import (  # noqa: E402
    apply_consensus,
    build_groups,
    skeleton,
)

FIELDS = ["name", "relation_name"]


def make_page(names: list[str], confidence: float = 0.98) -> Page:
    """One page whose records carry the given `relation_name` readings."""
    records = []
    for i, value in enumerate(names):
        records.append(
            Record(
                id=f"r{i}",
                page_id="p1",
                index=i,
                template_id="electoral_roll_ta",
                fields={
                    "name": FieldValue(key="name", original_value=f"person{i}",
                                       confidence=confidence),
                    "relation_name": FieldValue(key="relation_name",
                                                original_value=value,
                                                confidence=confidence),
                },
            )
        )
    return Page(id="p1", file_id="f1", page_number=1,
                template_id="electoral_roll_ta", records=records)


def relation_values(page: Page) -> list[str]:
    return [r.fields["relation_name"].value for r in page.records]


# ---------------------------------------------------------------------------
# Skeleton grouping
# ---------------------------------------------------------------------------


def test_skeleton_strips_vowel_signs():
    assert skeleton("இராகவன்") == skeleton("இரொகவன்")
    assert skeleton("சுரேஷ்") == skeleton("சுரெஷ்")
    assert skeleton("இராஜேந்திரன்") == skeleton("இராஜெந்திரன்")


def test_skeleton_keeps_pulli_so_distinct_names_stay_distinct():
    """The pulli is structural; stripping it would merge unrelated names."""
    assert skeleton("ராணி") != skeleton("ராண்")


def test_build_groups_buckets_variants_together():
    page = make_page(["இராகவன்", "இரொகவன்", "நாகராஜ்"])
    groups = build_groups(page.records, ["relation_name"])
    target = groups[skeleton("இராகவன்")]
    assert target.total == 2
    assert len(target.variants) == 2


# ---------------------------------------------------------------------------
# Decisive majority -> corrected
# ---------------------------------------------------------------------------


def test_decisive_majority_is_applied():
    """இராகவன் x5 vs இரொகவன் x1 -- the real 10_10 case."""
    page = make_page(["இராகவன்"] * 5 + ["இரொகவன்"])
    report = apply_consensus([page])

    assert report.suggestions == 1
    assert report.auto_applied == 1
    assert relation_values(page) == ["இராகவன்"] * 6


def test_correction_records_a_reviewable_issue():
    page = make_page(["இராகவன்"] * 5 + ["இரொகவன்"])
    apply_consensus([page])

    corrected = page.records[5].fields["relation_name"]
    codes = [i.code for i in corrected.issues]
    assert IssueCode.SPELLING_VARIANT.value in codes


def test_original_value_is_never_overwritten():
    """The raw OCR reading must stay recoverable for 'reset to original'."""
    page = make_page(["இராகவன்"] * 5 + ["இரொகவன்"])
    apply_consensus([page])

    corrected = page.records[5].fields["relation_name"]
    assert corrected.original_value == "இரொகவன்"
    assert corrected.edited_value == "இராகவன்"
    assert corrected.suggested_value == "இராகவன்"


def test_suggest_only_mode_leaves_values_untouched():
    page = make_page(["இராகவன்"] * 5 + ["இரொகவன்"])
    report = apply_consensus([page], auto_apply=False)

    assert report.suggestions == 1
    assert report.auto_applied == 0
    assert page.records[5].fields["relation_name"].suggested_value == "இராகவன்"
    assert page.records[5].fields["relation_name"].value == "இரொகவன்"


# ---------------------------------------------------------------------------
# Inconclusive votes -> left alone
#
# This is the safety property that matters most: a 2:1 majority pointing at
# the WRONG spelling really occurred in the corpus, so consensus must refuse
# to act on thin margins rather than corrupt a correct name.
# ---------------------------------------------------------------------------


def test_thin_majority_is_not_applied():
    """இராஜெந்திரன் x2 (wrong) vs இராஜேந்திரன் x1 (right) -- must not fire."""
    page = make_page(["இராஜெந்திரன்"] * 2 + ["இராஜேந்திரன்"])
    report = apply_consensus([page])

    assert report.suggestions == 0
    assert relation_values(page) == ["இராஜெந்திரன்", "இராஜெந்திரன்", "இராஜேந்திரன்"]
    assert any("unresolved" in d for d in report.details)


def test_even_split_is_not_applied():
    page = make_page(["சுரேஷ்", "சுரெஷ்"])
    report = apply_consensus([page])
    assert report.suggestions == 0


def test_group_below_minimum_size_is_ignored():
    page = make_page(["இரங்கசாமி", "இரெங்கசாமி"])
    report = apply_consensus([page])
    assert report.suggestions == 0


def test_unanimous_spelling_produces_no_conflict():
    page = make_page(["இராகவன்"] * 5)
    report = apply_consensus([page])
    assert report.groups_with_conflict == 0
    assert report.suggestions == 0


# ---------------------------------------------------------------------------
# Scope
# ---------------------------------------------------------------------------


def test_consensus_spans_multiple_pages():
    """Evidence accumulates across the batch, which is the whole point."""
    pages = [make_page(["இராகவன்", "இரொகவன்"]), make_page(["இராகவன்"] * 4)]
    report = apply_consensus(pages)

    assert report.auto_applied == 1
    assert relation_values(pages[0]) == ["இராகவன்", "இராகவன்"]


def test_identifiers_are_never_harmonised():
    """Every EPIC is unique; voting on them would destroy data."""
    page = make_page(["இராகவன்"] * 6)
    for i, record in enumerate(page.records):
        record.fields["epic"] = FieldValue(
            key="epic", original_value=f"ZHT000000{i}", confidence=0.99
        )
    apply_consensus([page])

    for i, record in enumerate(page.records):
        assert record.fields["epic"].value == f"ZHT000000{i}"
        assert record.fields["epic"].suggested_value is None


def test_disabled_consensus_is_a_no_op(monkeypatch):
    from app.services import consensus as consensus_module

    monkeypatch.setattr(consensus_module.settings, "consensus_enabled", False)
    page = make_page(["இராகவன்"] * 5 + ["இரொகவன்"])
    report = apply_consensus([page])

    assert report.suggestions == 0
    assert relation_values(page)[5] == "இரொகவன்"

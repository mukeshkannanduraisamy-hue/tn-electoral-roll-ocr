"""Which record wins when one elector appears more than once.

An EPIC is not unique across a promotion batch, and the duplicates are not
mistakes. A roll reprints an elector in its supplement to strike them off, and
the corpus holds two revisions of the same part. Promotion has to pick one row
per elector, and picking the wrong one silently loses a deletion -- an elector
struck off the roll stays active in the curated table, which is the kind of
error that looks like clean data.

The policy, in precedence order:

1. **A later revision wins.** Revision 2 supersedes Revision 1 outright, even
   where Revision 1 deleted an elector that Revision 2 carries as active --
   that is a reinstatement, not a deletion to preserve.
2. **A deletion wins.** Within one revision, the supplement's struck-off entry
   beats the main roll's active one, because the supplement is the later word
   on the same elector.
3. **A supplement wins.** Same reasoning, for entries the supplement re-lists
   without striking off.
4. **Otherwise the earlier entry wins**, which is the behaviour that was there
   before any of this: two misreads of one EPIC on a single page are
   indistinguishable, so the first is kept rather than the choice being made
   by whichever happened to sort last.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.routers.voters import (  # noqa: E402
    PromotionCandidate,
    resolve_deletions,
    resolve_duplicate_epics,
    revision_of,
)


def candidate(record_id, *, epic="ABC1234567", revision=2, is_deleted=False,
              is_supplement=False, page_number=4, index=0, is_clean=True,
              deletion_reason=""):
    return PromotionCandidate(
        record_id=record_id, epic=epic, revision=revision,
        is_deleted=is_deleted, is_supplement=is_supplement,
        page_number=page_number, index=index, is_clean=is_clean,
        deletion_reason=deletion_reason,
    )


# --------------------------------------------------------------- revision_of


@pytest.mark.parametrize("name,expected", [
    ("2026-FC-EROLLGEN-S22-58-SIR-FinalRoll-Revision2-TAM-15-WI.pdf", 2),
    ("2026-EROLLGEN-S22-58-SIR-FinalRoll-Revision1-TAM-2-WI.pdf", 1),
    ("2026-FC-EROLLGEN-S22-58-SIR-FinalRoll-Revision2-TAM-11-WI (1).pdf", 2),
    ("Revision 3 roll.pdf", 3),
    ("revision10-part-4.pdf", 10),
])
def test_the_revision_is_read_from_the_file_name(name, expected):
    """The only place it exists.

    The cover sheet yields `revision_year` (2026 for the whole corpus) and a
    `revision_type` that is the Tamil for "year of revision" -- neither
    distinguishes a first revision from a second. The publisher's file name
    does, consistently, across all 47 documents.
    """
    assert revision_of(name) == expected


def test_a_file_name_without_a_revision_sorts_below_every_real_one():
    """Unknown must lose to known, or an unnamed file could beat Revision 2."""
    assert revision_of("some-roll.pdf") == 0
    assert revision_of("") == 0
    assert revision_of(None) == 0


# ------------------------------------------------------------ the precedence


def test_a_supplement_deletion_beats_the_main_roll_entry():
    """The case that was losing 184 deletions."""
    main_roll = candidate("r-main", page_number=4)
    struck_off = candidate("r-supp", page_number=20,
                           is_deleted=True, is_supplement=True)

    winners = resolve_duplicate_epics([main_roll, struck_off])

    assert winners["ABC1234567"] == "r-supp"


def test_the_deletion_wins_regardless_of_which_page_is_scanned_first():
    """Order of arrival must not decide it -- that was the original bug."""
    main_roll = candidate("r-main", page_number=4)
    struck_off = candidate("r-supp", page_number=20, is_deleted=True)

    forward = resolve_duplicate_epics([main_roll, struck_off])
    reversed_ = resolve_duplicate_epics([struck_off, main_roll])

    assert forward == reversed_ == {"ABC1234567": "r-supp"}


def test_revision_2_beats_revision_1():
    old = candidate("r-old", revision=1)
    new = candidate("r-new", revision=2)

    assert resolve_duplicate_epics([old, new])["ABC1234567"] == "r-new"


def test_a_later_revision_outranks_an_earlier_revisions_deletion():
    """A reinstated elector.

    Revision 1 struck this elector off; Revision 2 lists them as active. The
    newer revision is the current state of the roll, so the deletion must not
    be carried forward -- otherwise a reinstatement can never be represented.
    """
    deleted_in_r1 = candidate("r-old", revision=1, is_deleted=True,
                              is_supplement=True, page_number=20)
    active_in_r2 = candidate("r-new", revision=2, page_number=4)

    winners = resolve_duplicate_epics([deleted_in_r1, active_in_r2])

    assert winners["ABC1234567"] == "r-new"


def test_a_supplement_beats_the_main_roll_even_without_a_deletion():
    """A re-listed elector is the supplement's more current reading."""
    main_roll = candidate("r-main", page_number=4)
    relisted = candidate("r-supp", page_number=20, is_supplement=True)

    assert resolve_duplicate_epics([main_roll, relisted])["ABC1234567"] == "r-supp"


def test_two_misreads_on_one_page_keep_the_first():
    """Nothing distinguishes them, so preserve the prior behaviour."""
    first = candidate("r-1", page_number=4, index=0)
    second = candidate("r-2", page_number=4, index=1)

    assert resolve_duplicate_epics([second, first])["ABC1234567"] == "r-1"


def test_an_earlier_page_wins_a_tie_across_pages():
    assert resolve_duplicate_epics([
        candidate("r-late", page_number=9),
        candidate("r-early", page_number=4),
    ])["ABC1234567"] == "r-early"


# ------------------------------------------------------------------ batching


def test_distinct_electors_are_all_winners():
    """Deduplication must only ever collapse a genuine collision."""
    winners = resolve_duplicate_epics([
        candidate("r-a", epic="AAA0000001"),
        candidate("r-b", epic="BBB0000002"),
        candidate("r-c", epic="CCC0000003"),
    ])
    assert winners == {
        "AAA0000001": "r-a", "BBB0000002": "r-b", "CCC0000003": "r-c",
    }


def test_an_empty_batch_resolves_to_nothing():
    assert resolve_duplicate_epics([]) == {}


# --------------------------------------------------------------- cleanliness


def test_a_clean_record_supplies_the_fields_over_an_unclean_deletion():
    """A struck-off cell reads badly -- the stamp costs the age line a digit.

    So the deletion is trustworthy as a *status* and untrustworthy as data.
    The clean main-roll entry keeps the name, age and house number; the
    deletion is carried separately by `resolve_deletions`.
    """
    clean_main = candidate("r-clean", page_number=4, is_clean=True)
    dirty_delete = candidate("r-dirty", page_number=20, is_deleted=True,
                             is_supplement=True, is_clean=False)

    assert resolve_duplicate_epics([clean_main, dirty_delete])["ABC1234567"] == "r-clean"


def test_cleanliness_does_not_outrank_the_revision():
    """Revision 2 is the current roll even where it reads worse."""
    clean_old = candidate("r-old", revision=1, is_clean=True)
    dirty_new = candidate("r-new", revision=2, is_clean=False)

    assert resolve_duplicate_epics([clean_old, dirty_new])["ABC1234567"] == "r-new"


def test_a_clean_deletion_still_wins_the_fields():
    """Cleanliness only decides between records of differing quality."""
    main = candidate("r-main", page_number=4)
    struck = candidate("r-supp", page_number=20, is_deleted=True)

    assert resolve_duplicate_epics([main, struck])["ABC1234567"] == "r-supp"


# ----------------------------------------------------------- deletion status


def test_an_unclean_deletion_still_marks_the_elector_deleted():
    """The case this exists for.

    187 records on the Penn corpus flag a deletion and fail validation. Under
    `only_clean` they were dropped entirely, so 160 electors the roll had
    struck off stayed active in the curated table.
    """
    clean_main = candidate("r-clean", page_number=4)
    dirty_delete = candidate("r-dirty", page_number=20, is_deleted=True,
                             is_clean=False, deletion_reason="S")

    assert resolve_deletions([clean_main, dirty_delete]) == {"ABC1234567": "S"}


def test_an_elector_nobody_deleted_is_absent_from_the_result():
    assert resolve_deletions([candidate("r-1"), candidate("r-2", epic="ZZZ9999999")]) == {}


def test_a_later_revision_reinstates_an_elector_deleted_earlier():
    """The deletion must not outlive the revision that made it.

    Revision 1 struck this elector off; Revision 2 lists them as active. Only
    the highest revision present for an elector gets a say, or a reinstatement
    could never be represented.
    """
    deleted_in_r1 = candidate("r-old", revision=1, is_deleted=True,
                              deletion_reason="S", is_supplement=True)
    active_in_r2 = candidate("r-new", revision=2)

    assert resolve_deletions([deleted_in_r1, active_in_r2]) == {}


def test_a_deletion_in_the_latest_revision_is_honoured():
    active_in_r1 = candidate("r-old", revision=1)
    deleted_in_r2 = candidate("r-new", revision=2, is_deleted=True,
                              deletion_reason="E", is_supplement=True)

    assert resolve_deletions([active_in_r1, deleted_in_r2]) == {"ABC1234567": "E"}


def test_a_deletion_with_no_stated_reason_is_still_a_deletion():
    """Presence in the mapping is the deletion; the reason is commentary."""
    result = resolve_deletions([
        candidate("r-1", is_deleted=True, deletion_reason=""),
    ])
    assert result == {"ABC1234567": ""}
    assert "ABC1234567" in result


def test_each_electors_deletion_is_decided_independently():
    result = resolve_deletions([
        candidate("a-main", epic="AAA0000001"),
        candidate("a-del", epic="AAA0000001", is_deleted=True,
                  is_clean=False, deletion_reason="R"),
        candidate("b-main", epic="BBB0000002"),
    ])
    assert result == {"AAA0000001": "R"}


def test_each_epic_is_resolved_independently():
    """One elector's supplement entry must not decide another's."""
    winners = resolve_duplicate_epics([
        candidate("a-main", epic="AAA0000001", page_number=4),
        candidate("a-supp", epic="AAA0000001", page_number=20, is_deleted=True),
        candidate("b-main", epic="BBB0000002", page_number=4),
    ])
    assert winners == {"AAA0000001": "a-supp", "BBB0000002": "b-main"}

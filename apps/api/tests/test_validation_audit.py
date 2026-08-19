"""The verification audit: which PDF is which, and when to trust the cache.

Two faults made this feature report confident nonsense.

**The wrong document.** A PDF was matched to its database file by exact name,
falling back to `LIKE %{stem[:30]}%`. Thirty characters of these filenames is
`2026-FC-EROLLGEN-S22-58-SIR-Fi` -- a prefix 35 of the 47 documents share,
because what distinguishes them (`-TAM-15-`) sits at the end. So one file's
electors were attributed to every document sharing its prefix, and the audit
reported 32,200 database records against a database holding 632.

**The stale answer.** `get_cached_audit` returned the cache file whenever it
existed, with nothing to invalidate it. After a re-extraction the panel kept
showing the previous run's verdict: 99.01% PASS from a cache against 93.42%
FAIL from a fresh scan of the same database, at the same moment.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.services.validator_service import (  # noqa: E402
    audit_fingerprint,
    file_match_pattern,
    parse_pdf_info,
)


@pytest.fixture()
def workspace():
    """A scratch directory.

    Not pytest's `tmp_path`, for the reason `test_photo_service` gives: its
    base is not writable on every machine this runs on, and it fails here with
    a PermissionError that has nothing to do with the test.
    """
    directory = Path(tempfile.mkdtemp(prefix="ocr-validation-"))
    try:
        yield directory
    finally:
        shutil.rmtree(directory, ignore_errors=True)


# Real names from the corpus, chosen to collide under the old prefix rule.
NAMES = [
    "2026-FC-EROLLGEN-S22-58-SIR-FinalRoll-Revision2-TAM-15-WI (1).pdf",
    "2026-FC-EROLLGEN-S22-58-SIR-FinalRoll-Revision2-TAM-16-WI (1).pdf",
    "2026-FC-EROLLGEN-S22-58-SIR-FinalRoll-Revision2-TAM-2-WI.pdf",
    "2026-FC-EROLLGEN-S22-58-SIR-FinalRoll-Revision2-TAM-286-WI.pdf",
    "2026-EROLLGEN-S22-30-SIR-FinalRoll-Revision1-TAM-2-WI.pdf",
    "2026-EROLLGEN-S22-30-SIR-FinalRoll-Revision1-TAM-10-WI.pdf",
    "2026-EROLLGEN-S22-57-SIR-FinalRoll-Revision1-TAM-4-WI.pdf",
]


# ------------------------------------------------------------ parse_pdf_info


@pytest.mark.parametrize("name,ac,part", [
    ("2026-FC-EROLLGEN-S22-58-SIR-FinalRoll-Revision2-TAM-15-WI (1).pdf", "58", "15"),
    ("2026-EROLLGEN-S22-30-SIR-FinalRoll-Revision1-TAM-10-WI.pdf", "30", "10"),
    ("2026-EROLLGEN-S22-57-SIR-FinalRoll-Revision1-TAM-4-WI.pdf", "57", "4"),
    ("2026-FC-EROLLGEN-S22-58-SIR-FinalRoll-Revision2-TAM-286-WI.pdf", "58", "286"),
])
def test_the_constituency_and_part_are_read_from_the_name(name, ac, part):
    assert parse_pdf_info(name) == (ac, part)


# -------------------------------------------------------- file_match_pattern


def test_the_pattern_distinguishes_documents_a_prefix_cannot():
    """The whole point: 35 documents shared the old 30-character prefix."""
    prefixes = {Path(n).stem[:30] for n in NAMES}
    patterns = {file_match_pattern(n) for n in NAMES}

    assert len(prefixes) < len(NAMES), "the names must actually collide by prefix"
    assert len(patterns) == len(NAMES), (
        f"patterns collided: {len(patterns)} distinct for {len(NAMES)} documents"
    )


def test_the_pattern_pins_both_the_constituency_and_the_part():
    """Part 2 of AC 58 and part 2 of AC 30 are different documents."""
    a = file_match_pattern("2026-FC-EROLLGEN-S22-58-SIR-FinalRoll-Revision2-TAM-2-WI.pdf")
    b = file_match_pattern("2026-EROLLGEN-S22-30-SIR-FinalRoll-Revision1-TAM-2-WI.pdf")
    assert a != b
    assert "58" in a and "30" in b


def test_the_pattern_does_not_let_part_2_match_part_286():
    """A trailing wildcard on the number would make 2 a prefix of 286."""
    import re

    pattern = file_match_pattern(
        "2026-FC-EROLLGEN-S22-58-SIR-FinalRoll-Revision2-TAM-2-WI.pdf"
    )
    # Translate the SQL LIKE into a regex to check what it would match.
    regex = re.compile("^" + ".*".join(re.escape(part) for part in pattern.split("%")) + "$")
    assert not regex.match("2026-FC-EROLLGEN-S22-58-SIR-FinalRoll-Revision2-TAM-286-WI.pdf")
    assert regex.match("2026-FC-EROLLGEN-S22-58-SIR-FinalRoll-Revision2-TAM-2-WI.pdf")


def test_a_name_with_no_part_number_yields_no_pattern():
    """Better no fallback than one that matches the whole table."""
    assert file_match_pattern("some-unrelated-document.pdf") is None


# ------------------------------------------------------------- cache staleness


def test_the_fingerprint_changes_when_the_data_changes():
    """What makes a cached verdict safe to serve."""
    a = audit_fingerprint(files=47, records=31951, voters=31212)
    b = audit_fingerprint(files=47, records=31951, voters=31212)
    c = audit_fingerprint(files=47, records=31951, voters=31213)

    assert a == b, "the same data must fingerprint identically"
    assert a != c, "one promoted elector must invalidate the cached audit"


def test_a_cache_without_a_fingerprint_is_not_trusted():
    """Caches written before this existed must not be served forever."""
    from app.services.validator_service import cache_is_current

    assert cache_is_current({}, "abc") is False
    assert cache_is_current({"summary": {}}, "abc") is False


def test_a_cache_is_served_only_for_the_data_it_describes():
    from app.services.validator_service import cache_is_current

    cached = {"summary": {}, "fingerprint": "abc"}
    assert cache_is_current(cached, "abc") is True
    assert cache_is_current(cached, "def") is False


def test_the_cache_file_carries_its_fingerprint(workspace, monkeypatch):
    """A written cache has to record what it was computed against."""
    from app.services import validator_service as vs

    cache = workspace / "audit.json"
    corpus = workspace / "corpus"
    corpus.mkdir()  # exists, holds no PDFs -- the scan runs and finds nothing
    monkeypatch.setattr(vs, "CACHE_FILE", cache)
    monkeypatch.setattr(vs, "PDF_DIR", corpus)

    vs.run_audit_scan()

    assert cache.exists(), "a scan must persist its result"
    written = json.loads(cache.read_text(encoding="utf-8"))
    assert written.get("fingerprint"), "the cache must record its fingerprint"


def test_a_missing_corpus_folder_is_reported_rather_than_shown_as_empty(
    workspace, monkeypatch
):
    """An empty panel reads as "no problems found"; this is a misconfiguration."""
    from app.services import validator_service as vs

    missing = workspace / "not-here"
    monkeypatch.setattr(vs, "PDF_DIR", missing)
    monkeypatch.setattr(vs, "CACHE_FILE", workspace / "audit.json")

    result = vs.run_audit_scan()

    assert result["reports"] == []
    assert "not-here" in result.get("error", ""), (
        "the missing folder must be named in the payload, not just the log"
    )

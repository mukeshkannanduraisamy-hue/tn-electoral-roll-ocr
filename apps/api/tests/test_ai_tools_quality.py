"""Data-quality tools.

These answer the question the workspace cannot currently ask: not "how many
electors are there" but "which of these records should I not believe".
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from app.db import (  # noqa: E402
    FileRow,
    PageRow,
    PollingStationRow,
    RecordRow,
    VoterRow,
    session_scope,
)
from app.services.ai_agent import registry  # noqa: E402
from app.services.ai_agent.tools import quality  # noqa: E402

PART = f"TEST-{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="module")
def sample_part():
    """One good record, one with an impossible age, one missing its gender —
    all three promoted from two real OCR records on one page, so
    ocr_quality(scope="part") has a genuine correlation to check rather than
    an empty one that happens to satisfy a loose assertion."""
    file_id = uuid.uuid4().hex
    page_id = uuid.uuid4().hex
    record_ids = [uuid.uuid4().hex, uuid.uuid4().hex]
    with session_scope() as s:
        s.add(FileRow(id=file_id, name="Quality Test File"))
        s.add(PageRow(id=page_id, file_id=file_id, page_number=1))
        s.add(
            RecordRow(
                id=record_ids[0], page_id=page_id, file_id=file_id, page_number=1,
                mean_confidence=0.9, min_confidence=0.8,
                error_count=1, warning_count=0, edited=False, reviewed=True,
            )
        )
        s.add(
            RecordRow(
                id=record_ids[1], page_id=page_id, file_id=file_id, page_number=1,
                mean_confidence=0.5, min_confidence=0.3,
                error_count=0, warning_count=2, edited=True, reviewed=False,
            )
        )
        s.add(
            VoterRow(
                id=uuid.uuid4().hex[:32], epic="TNAQ0000001", name="Good Record",
                age=45, gender="Male", house_number="12", part_number=PART,
                page_id=page_id, search_text="good",
            )
        )
        s.add(
            VoterRow(
                id=uuid.uuid4().hex[:32], epic="TNAQ0000002", name="Impossible Age",
                age=3, gender="Female", house_number="14", part_number=PART,
                page_id=page_id, search_text="impossible",
            )
        )
        s.add(
            VoterRow(
                id=uuid.uuid4().hex[:32], epic="TNAQ0000003", name="No Gender",
                age=30, gender="", part_number=PART,
                page_id=page_id, search_text="nogender",
            )
        )
    yield PART
    with session_scope() as s:
        for row in s.query(VoterRow).filter(VoterRow.part_number == PART).all():
            s.delete(row)
        for rid in record_ids:
            row = s.get(RecordRow, rid)
            if row:
                s.delete(row)
        page = s.get(PageRow, page_id)
        if page:
            s.delete(page)
        f = s.get(FileRow, file_id)
        if f:
            s.delete(f)


def _run(name, args):
    with session_scope() as s:
        return registry.execute(s, name, args)


def test_implausible_age_flags_only_the_child(sample_part):
    rows = _run("find_anomalies", {"kind": "implausible_age", "part_number": sample_part})["rows"]
    assert [r["epic"] for r in rows] == ["TNAQ0000002"]
    assert rows[0]["reason"]


def test_missing_field_flags_the_blank_gender(sample_part):
    rows = _run("find_anomalies", {"kind": "missing_field", "part_number": sample_part})["rows"]
    assert [r["epic"] for r in rows] == ["TNAQ0000003"]


def test_anomaly_rows_are_citable(sample_part):
    rows = _run("find_anomalies", {"kind": "implausible_age", "part_number": sample_part})["rows"]
    assert "id" in rows[0] and "epic" in rows[0]


def test_unknown_anomaly_kind_is_refused():
    with pytest.raises(registry.ToolError, match="Invalid arguments"):
        _run("find_anomalies", {"kind": "bad_vibes"})


def test_ocr_quality_for_a_part_reports_a_population(sample_part):
    result = _run("ocr_quality", {"scope": "part", "id": sample_part})
    assert result["population"] == 3
    # The two fixture records correlate to this part through their shared
    # page_id -- if that join silently matched nothing (e.g. an all-NULL
    # IN-list), these would read as 0 / None instead of the real values.
    assert result["records"] == 2
    assert result["mean_confidence"] == pytest.approx(0.7)
    assert result["min_confidence"] == pytest.approx(0.3)
    assert result["error_count"] == 1
    assert result["warning_count"] == 2
    assert result["edited"] == 1
    assert result["reviewed"] == 1


def test_low_confidence_records_respects_its_limit():
    result = _run("low_confidence_records", {"limit": 5})
    assert len(result["rows"]) <= 5


def _epic_field(value):
    return {
        "key": "epic", "original_value": value, "edited_value": None,
        "suggested_value": None, "confidence": 0.9, "bbox": None,
        "source_line_ids": [], "issues": [],
    }


def test_duplicate_epic_finds_the_pair():
    """Two OCR records that extracted the same EPIC (modulo case and
    whitespace) must surface as one duplicate group. Grouping on
    `search_text` (which flattens every field) would never find this, since
    the rest of each record's fields differ."""
    file_id = uuid.uuid4().hex
    page_id = uuid.uuid4().hex
    id_a = uuid.uuid4().hex
    id_b = uuid.uuid4().hex
    # Unique per run so this can never collide with a real duplicate EPIC.
    epic_value = f"DUP{uuid.uuid4().hex[:8].upper()}"

    with session_scope() as s:
        s.add(FileRow(id=file_id, name="Duplicate EPIC Test File"))
        s.add(PageRow(id=page_id, file_id=file_id, page_number=1))
        s.add(
            RecordRow(
                id=id_a, page_id=page_id, file_id=file_id, page_number=1,
                fields={"epic": _epic_field(f"  {epic_value.lower()}  ")},
            )
        )
        s.add(
            RecordRow(
                id=id_b, page_id=page_id, file_id=file_id, page_number=1,
                fields={"epic": _epic_field(epic_value)},
            )
        )
    try:
        rows = _run("find_anomalies", {"kind": "duplicate_epic", "limit": 50})["rows"]
        match = [r for r in rows if r["epic"] == epic_value]
        assert len(match) == 1
        assert match[0]["occurrences"] == 2
        assert set(match[0]["record_ids"]) == {id_a, id_b}
        assert match[0]["reason"]
    finally:
        with session_scope() as s:
            for rid in (id_a, id_b):
                row = s.get(RecordRow, rid)
                if row:
                    s.delete(row)
            page = s.get(PageRow, page_id)
            if page:
                s.delete(page)
            f = s.get(FileRow, file_id)
            if f:
                s.delete(f)


def test_epic_format_discloses_its_scan_bound():
    """A scan capped well below the ~3,500-elector corpus must say so --
    otherwise "no malformed EPICs" silently means "none in the fraction I
    looked at"."""
    result = _run("find_anomalies", {"kind": "epic_format"})
    assert "scanned" in result
    assert "truncated" in result
    assert result["scanned"] <= quality.EPIC_FORMAT_SCAN_LIMIT
    # The dev DB has ~3,473 electors, far more than the scan bound.
    assert result["truncated"] is True


def test_count_mismatch_finds_a_mismatch_beyond_the_scan_window():
    """A real mismatch must not go unreported merely because many
    never-mismatched stations are examined first: `limit` bounds mismatches
    *returned*, not stations *scanned*, and results are ordered by
    part_number rather than incidental DB row order."""
    with session_scope() as s:
        existing_total = s.execute(
            select(func.count()).select_from(PollingStationRow)
        ).scalar_one()

    file_id = uuid.uuid4().hex
    suffix = uuid.uuid4().hex[:8]
    filler_ids = [uuid.uuid4().hex for _ in range(10)]
    target_id = uuid.uuid4().hex
    target_part = f"ZZZTEST-{suffix}-target"

    with session_scope() as s:
        s.add(FileRow(id=file_id, name="Count Mismatch Test File"))
        for i, fid in enumerate(filler_ids):
            # declared_electors=0 is skipped by design (`if declared`), so
            # these can never register as mismatches themselves -- they only
            # exist to push the real mismatch further back in the scan.
            s.add(
                PollingStationRow(
                    id=fid, file_id=file_id,
                    part_number=f"ZZZTEST-{suffix}-filler-{i:02d}",
                    name=f"Filler Station {i}", total_electors=0,
                )
            )
        s.add(
            PollingStationRow(
                id=target_id, file_id=file_id, part_number=target_part,
                name="Mismatched Station", total_electors=42,
            )
        )

    # Large enough that our target still has budget even if every
    # pre-existing real station happened to be a mismatch; small enough
    # (well below existing_total + 11 synthetic rows) that a scan capped at
    # `limit` stations, rather than `limit` results, could plausibly have
    # missed the target entirely.
    limit = min(50, existing_total + 1)

    try:
        result = _run("find_anomalies", {"kind": "count_mismatch", "limit": limit})
        matches = [r for r in result["rows"] if r["part_number"] == target_part]
        assert len(matches) == 1
        assert matches[0]["declared_electors"] == 42
        assert matches[0]["extracted_electors"] == 0
        assert matches[0]["reason"]
    finally:
        with session_scope() as s:
            for sid in filler_ids + [target_id]:
                row = s.get(PollingStationRow, sid)
                if row:
                    s.delete(row)
            f = s.get(FileRow, file_id)
            if f:
                s.delete(f)

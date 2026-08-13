"""Pipeline and geography tools.

These let the assistant answer "what is the state of my corpus" — which files
are processed, which pages failed, what the roll covers — without the operator
navigating four different screens.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.db import FileRow, JobRow, PageRow, PollingStationRow, session_scope  # noqa: E402
from app.services.ai_agent import registry  # noqa: E402
from app.services.ai_agent.tools import geography, pipeline  # noqa: F401,E402


def _run(name, args):
    with session_scope() as s:
        return registry.execute(s, name, args)


def test_file_status_without_an_id_lists_every_file():
    result = _run("file_status", {})
    assert "files" in result
    assert isinstance(result["files"], list)


def test_file_status_refuses_an_unknown_file():
    with pytest.raises(registry.ToolError, match="No file"):
        _run("file_status", {"file_id": "definitely-not-a-file"})


def test_job_status_returns_a_list():
    assert isinstance(_run("job_status", {})["jobs"], list)


def test_roll_overview_reports_totals_and_coverage():
    result = _run("roll_overview", {})
    for key in ("voters", "files", "pages", "records", "parts", "constituencies"):
        assert key in result


def test_page_details_with_no_identifier_surveys_the_whole_corpus():
    """`page_details` used to refuse any call with neither `page_id` nor
    `file_id`, which meant a corpus-wide question like 'which pages failed
    OCR?' had no way to be asked at all. It must now run unscoped."""
    result = _run("page_details", {})
    assert "pages" in result
    assert isinstance(result["pages"], list)
    assert "total" in result and "truncated" in result


def test_polling_station_needs_an_identifier():
    with pytest.raises(registry.ToolError, match="part_number or station_id"):
        _run("polling_station", {})


# ---------------------------------------------------------------------------
# Truncation disclosure. `file_status` caps at 50 files, `page_details` at 50
# pages, `job_status` at 10 jobs, and `roll_overview` slices its parts and
# constituencies lists — a quietly partial answer from a tool whose whole job
# is reporting corpus state is worse than an error, so each cap must publish
# the true total and whether what came back was cut short.
# ---------------------------------------------------------------------------


def test_file_status_discloses_total_and_truncated_for_the_full_list():
    result = _run("file_status", {})
    assert "total" in result
    assert "truncated" in result
    # The dev corpus has 6 files, well under the 50-file cap.
    assert result["total"] == result["returned"]
    assert result["truncated"] is False


def test_file_status_discloses_total_for_a_single_file():
    files = _run("file_status", {})["files"]
    if not files:
        return
    any_file = files[0]
    result = _run("file_status", {"file_id": any_file["file_id"]})
    assert result["total"] == 1
    assert result["returned"] == 1
    assert result["truncated"] is False


def test_page_details_discloses_total_and_truncated():
    files = _run("file_status", {})["files"]
    if not files:
        return
    any_file = files[0]
    result = _run("page_details", {"file_id": any_file["file_id"]})
    assert "total" in result
    assert "truncated" in result
    assert result["truncated"] == (result["total"] > result["returned"])


def test_job_status_discloses_total_and_truncated_when_under_the_cap():
    result = _run("job_status", {})
    assert "total" in result
    assert "truncated" in result
    assert result["truncated"] == (result["total"] > result["returned"])


def test_job_status_truncated_is_true_once_jobs_exceed_the_cap():
    """job_status caps at 10 rows. With 11 jobs in the table, the 11th must
    not silently vanish -- `total` must exceed `returned` and `truncated`
    must say so, rather than reporting exactly 10 as if that were everything."""
    job_ids = [uuid.uuid4().hex for _ in range(11)]
    with session_scope() as s:
        for jid in job_ids:
            s.add(JobRow(id=jid, status="queued"))
    try:
        result = _run("job_status", {})
        assert result["returned"] == 10
        assert result["total"] >= 11
        assert result["truncated"] is True
    finally:
        with session_scope() as s:
            for jid in job_ids:
                row = s.get(JobRow, jid)
                if row:
                    s.delete(row)


def test_roll_overview_discloses_constituency_count_alongside_the_slice():
    """`part_count` already discloses the true number of parts behind the
    sliced `parts` list; `constituencies` is sliced the same way and must not
    be left silent."""
    result = _run("roll_overview", {})
    assert "constituency_count" in result
    assert result["constituency_count"] >= len(result["constituencies"])
    assert result["part_count"] >= len(result["parts"])


# ---------------------------------------------------------------------------
# Review findings (round 2): a never-captured declared total must not read as
# a real mismatch, and an unknown file must not be conflated with a real file
# that simply has no matching pages.
# ---------------------------------------------------------------------------


def test_polling_station_flags_a_never_captured_declared_total():
    """`total_electors` is a non-nullable Integer defaulting to 0, populated
    from one OCR pass over the part's cover sheet. When that OCR misses the
    totals line, 0 is indistinguishable at the column level from a part that
    genuinely declared zero -- so a zero declared total must not silently
    produce a numeric `difference` that reads as a real mismatch."""
    station_id = uuid.uuid4().hex
    file_id = uuid.uuid4().hex
    part = f"ZZZTEST-{uuid.uuid4().hex[:8]}-nodeclared"
    with session_scope() as s:
        s.add(FileRow(id=file_id, name="Zero Declared Test File"))
        s.add(
            PollingStationRow(
                id=station_id, file_id=file_id, part_number=part,
                name="No Declared Total Station", total_electors=0,
            )
        )
    try:
        result = _run("polling_station", {"part_number": part})
        assert result["declared"]["total_electors"] == 0
        assert result["declared"]["available"] is False
        assert result["difference"] is None
    finally:
        with session_scope() as s:
            row = s.get(PollingStationRow, station_id)
            if row:
                s.delete(row)
            f = s.get(FileRow, file_id)
            if f:
                s.delete(f)


def test_polling_station_reports_a_real_difference_when_declared_is_available():
    """The counterpart to the zero-declared case above: a nonzero declared
    total must still produce a real numeric `difference`, signed extracted
    minus declared."""
    station_id = uuid.uuid4().hex
    file_id = uuid.uuid4().hex
    part = f"ZZZTEST-{uuid.uuid4().hex[:8]}-declared"
    with session_scope() as s:
        s.add(FileRow(id=file_id, name="Declared Total Test File"))
        s.add(
            PollingStationRow(
                id=station_id, file_id=file_id, part_number=part,
                name="Declared Total Station", total_electors=900,
            )
        )
    try:
        result = _run("polling_station", {"part_number": part})
        assert result["declared"]["available"] is True
        # No electors were extracted for this synthetic part.
        assert result["difference"] == -900
    finally:
        with session_scope() as s:
            row = s.get(PollingStationRow, station_id)
            if row:
                s.delete(row)
            f = s.get(FileRow, file_id)
            if f:
                s.delete(f)


def test_page_details_refuses_an_unknown_file():
    with pytest.raises(registry.ToolError, match="No file"):
        _run("page_details", {"file_id": "definitely-not-a-file"})


def test_page_details_returns_empty_for_a_known_file_with_no_matching_pages():
    """A real file with no page matching the filter is a true, useful
    answer -- distinct from an unknown file -- and must not raise."""
    files = _run("file_status", {})["files"]
    if not files:
        return
    any_file = files[0]
    result = _run(
        "page_details", {"file_id": any_file["file_id"], "page_number": 999999}
    )
    assert result["pages"] == []
    assert result["returned"] == 0
    assert result["total"] == 0
    assert result["truncated"] is False


# ---------------------------------------------------------------------------
# Defect 1: "Which pages failed OCR?" -- page_details must be answerable with
# no page_id/file_id at all, scanning across every file, with failed_only and
# page_number honoured and results ordered deterministically (file then page
# number). An unknown file_id must still raise, unchanged.
# ---------------------------------------------------------------------------


def test_page_details_unscoped_returns_pages_across_multiple_files():
    file_a = "000000_" + uuid.uuid4().hex[:20]
    file_b = "000001_" + uuid.uuid4().hex[:20]
    page_a = uuid.uuid4().hex
    page_b = uuid.uuid4().hex
    with session_scope() as s:
        s.add(FileRow(id=file_a, name="Corpus Scan File A"))
        s.add(FileRow(id=file_b, name="Corpus Scan File B"))
        s.add(PageRow(id=page_a, file_id=file_a, page_number=1, status="done"))
        s.add(PageRow(id=page_b, file_id=file_b, page_number=1, status="done"))
    try:
        result = _run("page_details", {})
        ids = {p["page_id"] for p in result["pages"]}
        assert page_a in ids
        assert page_b in ids
        # Ordered deterministically by file then page number.
        file_ids_seen = [p["file_id"] for p in result["pages"]]
        assert file_ids_seen == sorted(file_ids_seen)
    finally:
        with session_scope() as s:
            for pid in (page_a, page_b):
                row = s.get(PageRow, pid)
                if row:
                    s.delete(row)
            for fid in (file_a, file_b):
                f = s.get(FileRow, fid)
                if f:
                    s.delete(f)


def test_page_details_unscoped_failed_only_returns_only_failed_pages():
    file_id = uuid.uuid4().hex
    ok_page = uuid.uuid4().hex
    failed_page = uuid.uuid4().hex
    with session_scope() as s:
        s.add(FileRow(id=file_id, name="Failed Only Scan File"))
        s.add(PageRow(id=ok_page, file_id=file_id, page_number=1, status="done"))
        s.add(
            PageRow(
                id=failed_page, file_id=file_id, page_number=2,
                status="failed", error="OCR timed out",
            )
        )
    try:
        result = _run("page_details", {"failed_only": True})
        ids = {p["page_id"] for p in result["pages"]}
        assert failed_page in ids
        assert ok_page not in ids
        assert all(p["status"] == "failed" for p in result["pages"])
    finally:
        with session_scope() as s:
            for pid in (ok_page, failed_page):
                row = s.get(PageRow, pid)
                if row:
                    s.delete(row)
            f = s.get(FileRow, file_id)
            if f:
                s.delete(f)


def test_page_details_unscoped_still_raises_for_an_unknown_file_id():
    """The unscoped path is a separate branch from the file_id branch; this
    guards against a regression that accidentally routed a real file_id
    argument into the "no identifier" survey instead of validating it."""
    with pytest.raises(registry.ToolError, match="No file"):
        _run("page_details", {"file_id": "definitely-not-a-file"})

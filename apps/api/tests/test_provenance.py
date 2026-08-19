"""OCR blocks and the audit trail.

Between them these answer "where did this value come from, and who has
touched it since" -- the two questions an electoral roll has to be able to
answer about any elector.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.db import (  # noqa: E402
    AuditLogRow,
    FileRow,
    OCRBlockRow,
    PageRow,
    RecordRow,
    VoterRow,
    _ocr_blocks_for,
    record_audit,
    row_to_record,
    save_page,
    session_scope,
)
from app.schemas.core import (  # noqa: E402
    BBox, FieldValue, OcrLine, Page, Record, normalize_box,
)


# ---------------------------------------------------------------------------
# The 0-1000 contract
# ---------------------------------------------------------------------------


def test_normalize_box_scales_to_the_grid():
    assert normalize_box(0, 0, 500, 400, 1000, 800) == [0, 0, 500, 500]


def test_normalize_box_is_resolution_independent():
    """The same region of the same page must normalise identically at any DPI."""
    at_150 = normalize_box(100, 200, 300, 400, 1187, 1680)
    at_300 = normalize_box(200, 400, 600, 800, 2374, 3360)
    assert at_150 == at_300


def test_normalize_box_clamps_out_of_bounds():
    assert normalize_box(-50, -50, 5000, 5000, 1000, 1000) == [0, 0, 1000, 1000]


def test_normalize_box_never_returns_a_flat_box():
    """A region thinner than a thousandth of the page still needs area."""
    x0, y0, x1, y1 = normalize_box(10, 10, 10, 10, 1000, 1000)
    assert x0 < x1 and y0 < y1


def test_normalize_box_survives_a_zero_sized_page():
    assert normalize_box(0, 0, 10, 10, 0, 0) == [0, 0, 1000, 1000]


def test_bbox_to_layoutlm_matches_normalize_box():
    box = BBox(x=100, y=200, w=200, h=200)
    assert box.to_layoutlm(1187, 1680) == normalize_box(100, 200, 300, 400, 1187, 1680)


# ---------------------------------------------------------------------------
# Block generation
# ---------------------------------------------------------------------------


def make_record(**fields: FieldValue) -> Record:
    return Record(
        id=uuid.uuid4().hex[:12],
        page_id="page1",
        index=0,
        template_id="electoral_roll_ta",
        fields=fields,
    )


def make_page(records: list[Record]) -> Page:
    return Page(
        id="page1",
        file_id="file1",
        page_number=4,
        width=1187,
        height=1680,
        page_type="voter_list_page",
        records=records,
    )


def test_blocks_are_emitted_per_located_field():
    record = make_record(
        epic=FieldValue(key="epic", original_value="ZHT0149526", confidence=0.99,
                        bbox=BBox(x=306, y=61, w=90, h=16)),
        name=FieldValue(key="name", original_value="பிரேமா", confidence=0.94,
                        bbox=BBox(x=36, y=86, w=120, h=16)),
    )
    blocks = list(_ocr_blocks_for(record, make_page([record])))
    assert {b.field_name for b in blocks} == {"epic", "name"}
    assert all(0 <= b.bbox_x0 < b.bbox_x1 <= 1000 for b in blocks)
    assert all(0 <= b.bbox_y0 < b.bbox_y1 <= 1000 for b in blocks)


def test_a_field_the_template_never_found_gets_no_block():
    """Otherwise every miss becomes a phantom highlight at the page origin."""
    record = make_record(
        epic=FieldValue(key="epic", original_value="ZHT0149526", confidence=0.99,
                        bbox=BBox(x=306, y=61, w=90, h=16)),
        age=FieldValue(key="age"),  # never located
    )
    blocks = list(_ocr_blocks_for(record, make_page([record])))
    assert [b.field_name for b in blocks] == ["epic"]


def test_a_corrected_value_is_kept_alongside_the_original():
    field = FieldValue(
        key="name", original_value="பிரேமோ", edited_value="பிரேமா",
        confidence=0.94, bbox=BBox(x=36, y=86, w=120, h=16),
    )
    record = make_record(name=field)
    block = next(iter(_ocr_blocks_for(record, make_page([record]))))
    assert block.raw_text == "பிரேமோ"
    assert block.corrected_text == "பிரேமா"


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


@pytest.fixture()
def stored_file():
    file_id = "t" + uuid.uuid4().hex[:11]
    with session_scope() as session:
        session.add(FileRow(id=file_id, name="test.pdf", page_count=1))
    yield file_id
    with session_scope() as session:
        session.query(OCRBlockRow).filter(
            OCRBlockRow.page_id.in_(
                session.query(PageRow.id).filter(PageRow.file_id == file_id)
            )
        ).delete(synchronize_session=False)
        session.query(RecordRow).filter(RecordRow.file_id == file_id).delete(
            synchronize_session=False
        )
        session.query(PageRow).filter(PageRow.file_id == file_id).delete(
            synchronize_session=False
        )
        session.query(FileRow).filter(FileRow.id == file_id).delete(
            synchronize_session=False
        )


def test_saving_a_page_does_not_persist_its_blocks(stored_file):
    """Blocks are built but not stored, and that is deliberate.

    `save_page` wrote one `OCRBlockRow` per located field until d521a23 took
    the write out: at thirty records a page and seven fields a record it was
    the bulk of what a roll cost to ingest, for a table nothing reads. The
    provenance the review workflow actually uses -- original value, edited
    value, confidence, bbox -- lives on the record itself and is unaffected.

    `_ocr_blocks_for` is deliberately left intact and still tested above, so
    restoring persistence is re-adding the write, not rebuilding the mapping.
    """
    record = make_record(
        epic=FieldValue(key="epic", original_value="ZHT0149526", confidence=0.99,
                        bbox=BBox(x=306, y=61, w=90, h=16)),
        name=FieldValue(key="name", original_value="பிரேமா", confidence=0.94,
                        bbox=BBox(x=36, y=86, w=120, h=16)),
    )
    page = make_page([record])
    page.id = "pg" + uuid.uuid4().hex[:10]
    record.page_id = page.id

    with session_scope() as session:
        save_page(session, page, stored_file)

    with session_scope() as session:
        blocks = session.query(OCRBlockRow).filter(
            OCRBlockRow.page_id == page.id
        ).all()
        assert blocks == []

    # The values themselves still survive the round trip -- this is a storage
    # decision about the blocks table, not about provenance as such.
    with session_scope() as session:
        saved = session.query(RecordRow).filter(
            RecordRow.page_id == page.id
        ).all()
        assert len(saved) == 1


def test_line_polygons_are_not_persisted(stored_file):
    """Four corners per line that nothing ever reads.

    `ocr_service` records both a `bbox` and the raw detection `polygon` for
    every line. Everything downstream uses the bbox -- cell assignment goes
    through `bbox.cx/cy`, the page overlay draws `bbox`, the text panel reads
    `text` -- and no code path in the API or the web app touches `polygon`.
    On the Penn corpus it was 17.2 MB across 275,198 lines, 22.8% of the page
    payload, serialised and written on every save and re-read by every
    post-processing pass.

    The field survives on the wire contract so the TypeScript type still
    holds; it is the stored values that go.
    """
    page = make_page([])
    page.id = "pg" + uuid.uuid4().hex[:10]
    page.lines = [
        OcrLine(
            id="ln1", text="பிரேமா", confidence=0.94,
            bbox=BBox(x=36, y=86, w=120, h=16),
            polygon=[(36, 86), (156, 86), (156, 102), (36, 102)],
        )
    ]

    with session_scope() as session:
        save_page(session, page, stored_file)

    with session_scope() as session:
        row = session.get(PageRow, page.id)
        stored_lines = (row.payload or {}).get("lines") or []
        assert len(stored_lines) == 1
        assert stored_lines[0]["polygon"] == []
        # The parts the UI actually renders must survive untouched.
        assert stored_lines[0]["text"] == "பிரேமா"
        assert stored_lines[0]["bbox"]["x"] == 36
        assert stored_lines[0]["bbox"]["w"] == 120


def test_field_bboxes_are_not_persisted(stored_file):
    """Per-field geometry with no reader left.

    `_ocr_blocks_for` is the only thing that consumes it, and its output has
    not been written since d521a23 -- so `/voters/{id}/ocr-blocks` already
    returns an empty list for every elector, and the boxes feeding it went
    nowhere. Nothing in the web app reads them either; the page overlay works
    off line bboxes and the cell box below.

    The cell box on the record itself is a different thing and is kept: the
    voter profile crops the elector's cell out of the page with it.
    """
    record = make_record(
        epic=FieldValue(key="epic", original_value="ZHT0149526", confidence=0.99,
                        bbox=BBox(x=306, y=61, w=90, h=16)),
        name=FieldValue(key="name", original_value="பிரேமா", confidence=0.94,
                        bbox=BBox(x=36, y=86, w=120, h=16)),
    )
    record.bbox = BBox(x=20, y=50, w=380, h=150)
    page = make_page([record])
    page.id = "pg" + uuid.uuid4().hex[:10]
    record.page_id = page.id

    with session_scope() as session:
        save_page(session, page, stored_file)

    with session_scope() as session:
        row = session.query(RecordRow).filter(RecordRow.page_id == page.id).one()
        assert row.fields["epic"]["bbox"] is None
        assert row.fields["name"]["bbox"] is None
        # Everything the review workflow reads survives.
        assert row.fields["epic"]["original_value"] == "ZHT0149526"
        assert row.fields["name"]["original_value"] == "பிரேமா"
        assert row.fields["name"]["confidence"] == 0.94
        # The cell box is a separate column and is still stored.
        assert row.bbox is not None
        assert row.bbox["x"] == 20 and row.bbox["w"] == 380


def test_a_record_survives_the_round_trip_without_field_bboxes(stored_file):
    """Reload has to work, since consensus and promotion both go through it."""
    record = make_record(
        name=FieldValue(key="name", original_value="பிரேமா", confidence=0.94,
                        bbox=BBox(x=36, y=86, w=120, h=16)),
    )
    page = make_page([record])
    page.id = "pg" + uuid.uuid4().hex[:10]
    record.page_id = page.id

    with session_scope() as session:
        save_page(session, page, stored_file)

    with session_scope() as session:
        row = session.query(RecordRow).filter(RecordRow.page_id == page.id).one()
        restored = row_to_record(row)

    assert restored.fields["name"].original_value == "பிரேமா"
    assert restored.fields["name"].bbox is None


def test_stripping_field_bboxes_leaves_the_in_memory_record_alone(stored_file):
    """Same contract as the polygons: saving must not reach into the caller."""
    record = make_record(
        name=FieldValue(key="name", original_value="x", confidence=0.9,
                        bbox=BBox(x=36, y=86, w=120, h=16)),
    )
    page = make_page([record])
    page.id = "pg" + uuid.uuid4().hex[:10]
    record.page_id = page.id

    with session_scope() as session:
        save_page(session, page, stored_file)

    assert record.fields["name"].bbox is not None
    assert record.fields["name"].bbox.x == 36


def test_stripping_polygons_leaves_the_in_memory_page_alone(stored_file):
    """Saving is not allowed to mutate what the caller handed over.

    The job pipeline saves a page and then hands the same object to consensus
    and section reconciliation. A save that reached into it would be a
    spooky action at a distance.
    """
    page = make_page([])
    page.id = "pg" + uuid.uuid4().hex[:10]
    polygon = [(36, 86), (156, 86), (156, 102), (36, 102)]
    page.lines = [
        OcrLine(id="ln1", text="x", confidence=0.9,
                bbox=BBox(x=36, y=86, w=120, h=16), polygon=list(polygon))
    ]

    with session_scope() as session:
        save_page(session, page, stored_file)

    assert [tuple(p) for p in page.lines[0].polygon] == polygon


def test_reprocessing_a_page_cannot_accumulate_blocks(stored_file):
    """The original risk was blocks piling up on every re-run.

    With the write gone the count is zero rather than one, but the property
    worth holding is the same: re-processing a page must not leave the blocks
    table growing behind it.
    """
    page_id = "pg" + uuid.uuid4().hex[:10]

    for _ in range(3):
        record = make_record(
            epic=FieldValue(key="epic", original_value="ZHT0149526",
                            confidence=0.99, bbox=BBox(x=306, y=61, w=90, h=16)),
        )
        record.page_id = page_id
        page = make_page([record])
        page.id = page_id
        with session_scope() as session:
            save_page(session, page, stored_file)

    with session_scope() as session:
        blocks = session.query(OCRBlockRow).filter(
            OCRBlockRow.page_id == page_id
        ).all()
        assert blocks == [], "blocks accumulated across re-processing"


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------


@pytest.fixture()
def voter():
    voter_id = "v" + uuid.uuid4().hex[:11]
    with session_scope() as session:
        session.add(
            VoterRow(
                id=voter_id,
                epic=f"ZHT{uuid.uuid4().int % 10_000_000:07d}",
                name="பிரேமா",
                age=41,
            )
        )
    yield voter_id
    with session_scope() as session:
        session.query(AuditLogRow).filter(
            AuditLogRow.voter_id == voter_id
        ).delete(synchronize_session=False)
        session.query(VoterRow).filter(VoterRow.id == voter_id).delete(
            synchronize_session=False
        )


def test_record_audit_writes_an_entry(voter):
    with session_scope() as session:
        record_audit(
            session, voter, action="updated", user="reviewer",
            field_name="age", old_value="41", new_value="45",
        )

    with session_scope() as session:
        entry = session.query(AuditLogRow).filter(
            AuditLogRow.voter_id == voter
        ).one()
        assert entry.action == "updated"
        assert (entry.field_name, entry.old_value, entry.new_value) == ("age", "41", "45")
        assert entry.user_id == "reviewer"
        assert entry.timestamp is not None


def test_audit_entries_outlive_the_voter_they_describe(voter):
    """"Who deleted this elector" is the question the trail exists to answer."""
    with session_scope() as session:
        record_audit(session, voter, action="deleted", user="reviewer",
                     old_value="ZHT0149526 பிரேமா")
        session.query(VoterRow).filter(VoterRow.id == voter).delete(
            synchronize_session=False
        )

    with session_scope() as session:
        assert session.get(VoterRow, voter) is None
        assert session.query(AuditLogRow).filter(
            AuditLogRow.voter_id == voter
        ).count() == 1

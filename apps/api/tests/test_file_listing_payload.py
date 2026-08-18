"""The file list must not drag the stored PDF bytes along with it.

Context: ``FileRow.file_data`` holds a base64 copy of the whole PDF (~1.33x the
16 MB source documents this project ingests). ``file_to_schema`` never reads it
and ``SourceFile`` has no field for it, but a plain ``select(FileRow)`` loads
every mapped column -- so listing N files streamed N * ~21 MB of base64 out of
Postgres only to discard it. Against a remote pooler that took ~133 s and died
with "SSL connection has been closed unexpectedly", surfacing in the UI as
"Failed to fetch files".

Nothing in the application reads ``file_data``, so it stays out of the default
load and these tests pin that down.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.inspection import inspect  # noqa: E402

from app.db import FileRow  # noqa: E402


def test_default_file_query_omits_the_pdf_blob():
    """`select(FileRow)` is what the list endpoint runs; keep the blob out."""
    sql = str(select(FileRow))
    assert "file_data" not in sql, (
        "listing files would stream the base64 PDF for every row:\n" + sql
    )


def test_metadata_the_list_response_needs_is_still_loaded():
    """Deferring must not accidentally push the real payload out of the query."""
    sql = str(select(FileRow))
    for column in (
        "id",
        "name",
        "size_bytes",
        "page_count",
        "status",
        "pages_done",
        "template_id",
        "languages",
        "error",
        "created_at",
    ):
        assert f"files.{column}" in sql, f"{column} missing from file list query"


def test_file_data_remains_reachable_when_explicitly_asked_for():
    """Deferred, not dropped: the column still exists for writers."""
    assert "file_data" in inspect(FileRow).columns.keys()

"""Guards on destructive file operations.

Context: `import-folder` registers PDFs *in place* rather than copying them,
so `FileRow.stored_path` may point at a document the user owns and expects
to keep. Removing a file from the workspace must never delete it from disk
in that case. A regression here silently destroys the source corpus, so it
gets its own test file.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.config import settings  # noqa: E402
from app.routers.files import _is_managed_upload  # noqa: E402


def test_uploaded_file_is_managed():
    """A PDF copied into uploads/ is ours and may be deleted."""
    target = settings.uploads_dir / "abc123.pdf"
    assert _is_managed_upload(str(target)) is True


def test_imported_source_file_is_not_managed():
    """A PDF referenced where the user keeps it must never be deleted."""
    external = settings.data_dir.parent / "PDF" / "2026-EROLLGEN" / "10_10.pdf"
    assert _is_managed_upload(str(external)) is False


def test_sibling_directory_is_not_managed():
    """A path that merely shares a prefix with uploads/ is still external."""
    sibling = settings.uploads_dir.parent / "uploads_backup" / "x.pdf"
    assert _is_managed_upload(str(sibling)) is False


def test_traversal_out_of_uploads_is_not_managed():
    """`uploads/../PDF/x.pdf` resolves outside uploads and must be refused."""
    escaped = settings.uploads_dir / ".." / "PDF" / "10_10.pdf"
    assert _is_managed_upload(str(escaped)) is False


@pytest.mark.parametrize("value", ["", None])
def test_empty_path_is_not_managed(value):
    assert _is_managed_upload(value) is False


def test_real_corpus_path_is_not_managed():
    """The concrete shape of the bug: the user's own electoral-roll PDFs."""
    assert _is_managed_upload(
        r"D:\OCR\PDF\2026-EROLLGEN-S22-57-SIR-FinalRoll-Revision1-TAM-10-WI\10_10.pdf"
    ) is False

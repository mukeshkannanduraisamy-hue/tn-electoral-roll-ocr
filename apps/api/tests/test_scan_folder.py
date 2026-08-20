import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from app.db import session_scope
from app.routers.files import scan_folder
from app.schemas.core import FolderScanRequest


def test_scan_folder_valid_dir():
    with tempfile.TemporaryDirectory() as tmp_dir:
        pdf_path = Path(tmp_dir) / "sample1.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 mock pdf content")

        with session_scope() as session:
            req = FolderScanRequest(path=tmp_dir, recursive=True)
            res = scan_folder(req, session=session)
            assert res.total_files == 1
            assert res.items[0].name == "sample1.pdf"
            assert res.items[0].is_registered is False
            assert res.items[0].status == "unregistered"


def test_scan_folder_nonexistent_dir():
    with session_scope() as session:
        req = FolderScanRequest(path="C:\\nonexistent_folder_xyz_123", recursive=False)
        with pytest.raises(Exception):
            scan_folder(req, session=session)


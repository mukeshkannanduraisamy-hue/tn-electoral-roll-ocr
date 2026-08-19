"""Image extraction is off, and these tests hold it off.

Station imagery and voter photographs were both disabled in d521a23 to keep
the database small -- the base64 copies dominated row size for something the
review workflow never reads. `photo_service` explains the decision and points
at 59cd3be for the implementation that was removed.

What is worth testing about a disabled feature is that it is disabled
*quietly*: the pipeline still calls `extract_station_photos` on a map sheet,
so the stub has to return an empty list for any input rather than raise, or a
map sheet fails the page. These tests pin that contract, and they will fail
the moment someone restores a real implementation without revisiting the
storage decision that motivated turning it off.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from app.schemas.core import BBox, OcrLine  # noqa: E402
from app.services.photo_service import (  # noqa: E402
    extract_station_photos,
    extract_voter_photo,
)

PAGE_W, PAGE_H = 1187, 1680
CELL = BBox(x=40, y=200, w=380, h=150)


@pytest.fixture()
def photos_dir():
    """A scratch output directory.

    Not pytest's `tmp_path`: its base directory is not writable on every
    machine this runs on, and a fixture that cannot create a folder fails
    every test in the module for a reason that has nothing to do with them.
    """
    directory = Path(tempfile.mkdtemp(prefix="ocr-photos-"))
    try:
        yield directory
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def _line(text: str, x: float, y: float) -> OcrLine:
    return OcrLine(
        id=text[:8],
        text=text,
        confidence=0.99,
        bbox=BBox(x=x, y=y, w=180, h=18),
    )


def _page() -> np.ndarray:
    return np.full((PAGE_H, PAGE_W, 3), 255, dtype=np.uint8)


def test_a_map_sheet_yields_no_station_imagery(photos_dir):
    """Captions that once located six panels now locate nothing."""
    lines = [
        _line("Nazri Naksha", 60, 120),
        _line("Google Map", 640, 120),
        _line("Building Front", 60, 700),
    ]
    assert extract_station_photos(lines, _page(), "page3", photos_dir) == []


def test_station_extraction_survives_input_it_cannot_read(photos_dir):
    """The pipeline calls this inside a page it still intends to complete.

    No captions, no lines at all, a zero-sized image: none of it may raise,
    because a map sheet that throws here takes the whole page to ERROR.
    """
    assert extract_station_photos([], _page(), "page3", photos_dir) == []
    assert extract_station_photos([], np.zeros((0, 0, 3), np.uint8), "p", photos_dir) == []


def test_no_voter_photograph_is_cropped(photos_dir):
    """Including from a cell whose box holds a real-looking dark region."""
    image = _page()
    image[220:340, 320:400] = 30  # ink where the photo box sits
    lines = [_line("Photo is available", 330, 240)]
    assert extract_voter_photo(CELL, lines, image, "page4", "rec1", photos_dir) is None
    assert extract_voter_photo(CELL, [], image, "page4", "rec1", photos_dir) is None


def test_nothing_is_written_to_disk(photos_dir):
    """The storage cost is the reason this is off, so assert the cost is zero."""
    lines = [_line("Nazri Naksha", 60, 120), _line("Google Map", 640, 120)]
    extract_station_photos(lines, _page(), "page3", photos_dir)
    extract_voter_photo(CELL, lines, _page(), "page4", "rec1", photos_dir)
    assert list(photos_dir.iterdir()) == []

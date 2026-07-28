"""Cropping images out of roll pages.

The load-bearing behaviour here is what *isn't* extracted: a published SIR
roll prints "Photo is available" in every voter's photo box, and a crop of
that sentence is worse than no crop at all.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from app.schemas.core import BBox, OcrLine  # noqa: E402
from app.services.photo_service import (  # noqa: E402
    STATION_CAPTIONS,
    extract_station_photos,
    extract_voter_photo,
    voter_photo_region,
)

PAGE_W, PAGE_H = 1187, 1680


@pytest.fixture()
def photos_dir():
    """A scratch output directory.

    Not pytest's `tmp_path`: its base directory is not writable on every
    machine this runs on, and a fixture that cannot create a folder fails
    every test in the module for a reason that has nothing to do with them.
    """
    directory = Path(tempfile.mkdtemp(prefix="ocr-photos-"))
    try:
        yield directory / "photos"
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def line(text: str, y: float, x: float, w: float = 200.0, h: float = 16.0) -> OcrLine:
    return OcrLine(
        id=uuid.uuid4().hex[:8], text=text, confidence=0.95,
        bbox=BBox(x=x, y=y, w=w, h=h), polygon=[],
    )


def blank_page() -> np.ndarray:
    return np.full((PAGE_H, PAGE_W, 3), 255, dtype=np.uint8)


def paint(image: np.ndarray, box: tuple[int, int, int, int], seed: int = 0) -> None:
    """Fill a region with varied pixels, standing in for a photograph."""
    x, y, w, h = box
    rng = np.random.default_rng(seed)
    image[y:y + h, x:x + w] = rng.integers(0, 200, size=(h, w, 3), dtype=np.uint8)


# ---------------------------------------------------------------------------
# Station imagery
# ---------------------------------------------------------------------------


def test_each_captioned_panel_is_cropped(photos_dir: Path):
    image = blank_page()
    captions = [
        ("Nazri Naksha", 61, 242), ("Google Map View", 59, 791),
        ("Polling Station Building Front View", 436, 138),
        ("Polling Station Front View", 436, 750),
        ("Cad View", 828, 260), ("Key MAP View", 827, 804),
    ]
    lines = [line(t, y, x) for t, y, x in captions]
    # A picture below each caption, in that caption's half of the sheet.
    for i, (_t, y, x) in enumerate(captions):
        left = 100 if x < PAGE_W / 2 else 700
        paint(image, (left, int(y) + 60, 300, 240), seed=i)

    photos = extract_station_photos(lines, image, "page3", photos_dir)

    assert {p.photo_type for p in photos} == set(STATION_CAPTIONS.values())
    assert all(p.width > 60 and p.height > 60 for p in photos)
    assert all((photos_dir / p.file_path).is_file() for p in photos)
    assert all(p.page_id == "page3" for p in photos)


def test_a_page_without_captions_yields_nothing(photos_dir: Path):
    photos = extract_station_photos(
        [line("பெயர் : சுசீலா", 100, 40)], blank_page(), "page4", photos_dir
    )
    assert photos == []


def test_a_caption_with_no_picture_beneath_it_is_skipped(photos_dir: Path):
    """A caption is not evidence of an image; the pixels are."""
    photos = extract_station_photos(
        [line("Nazri Naksha", 61, 242)], blank_page(), "page3", photos_dir
    )
    assert photos == []


# ---------------------------------------------------------------------------
# Voter photographs
# ---------------------------------------------------------------------------

CELL = BBox(x=30, y=57, w=367, h=146)


def test_the_photo_region_sits_inside_its_cell():
    region = voter_photo_region(CELL)
    assert CELL.x <= region.x and region.x2 <= CELL.x2
    assert CELL.y <= region.y and region.y2 <= CELL.y2
    # Right-hand side, clear of the serial/EPIC line along the top.
    assert region.cx > CELL.cx
    assert region.y > CELL.y


def test_a_placeholder_box_produces_no_crop(photos_dir: Path):
    """The behaviour this module exists for: a printed 'Photo is available'
    box holds no photograph, whatever its ink statistics look like."""
    image = blank_page()
    region = voter_photo_region(CELL)
    paint(image, (int(region.x), int(region.y), int(region.w), int(region.h)))

    lines = [
        line("Photo is", region.cy - 10, region.x + 4, w=60),
        line("available", region.cy + 10, region.x + 4, w=60),
    ]
    photo = extract_voter_photo(CELL, lines, image, "page4", "rec1", photos_dir)

    assert photo is None
    assert not photos_dir.exists() or not list(photos_dir.glob("*.png"))


def test_a_real_photograph_is_cropped(photos_dir: Path):
    image = blank_page()
    region = voter_photo_region(CELL)
    paint(image, (int(region.x), int(region.y), int(region.w), int(region.h)))

    photo = extract_voter_photo(CELL, [], image, "page4", "rec1", photos_dir)

    assert photo is not None
    assert photo.photo_type == "voter_crop"
    assert photo.record_id == "rec1"
    assert (photos_dir / photo.file_path).is_file()


def test_an_empty_box_produces_no_crop(photos_dir: Path):
    """Nothing printed and nothing drawn: there is no photograph."""
    assert extract_voter_photo(CELL, [], blank_page(), "page4", "rec1", photos_dir) is None


def test_placeholder_text_outside_the_region_does_not_suppress_a_crop(photos_dir: Path):
    """Only text *inside* the box speaks to what the box holds."""
    image = blank_page()
    region = voter_photo_region(CELL)
    paint(image, (int(region.x), int(region.y), int(region.w), int(region.h)))

    # "Photo is available" printed in a neighbouring cell entirely.
    far_away = [line("Photo is available", CELL.y + 10, CELL.x2 + 200, w=80)]
    photo = extract_voter_photo(CELL, far_away, image, "page4", "rec1", photos_dir)

    assert photo is not None

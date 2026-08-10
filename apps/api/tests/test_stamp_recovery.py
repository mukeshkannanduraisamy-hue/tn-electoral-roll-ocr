"""Recovering a stamped elector's age by agreement, not by a tuned crop.

Reading a narrower crop of the cell often recovers the digit the stamp cost --
`59` instead of `5` -- but *which* width works is erratic. Measured on three real
cards, ages recovered at crop fractions 0.45 and 0.55 and failed at 0.50, 0.60 and
0.65. That is the recognizer's internal resizing, not a property of the card, so a
hard-coded fraction would be fitted to three samples and would move under a
different DPI or PaddleOCR build.

So no fraction is chosen. Several are read, readings that cannot be an age are
discarded, and a value is accepted only when the survivors agree. On the three
cards the implausible readings are exactly the damaged ones (`5`, `4`, `3`, all
under MIN_AGE), and what survives is unanimous.

The known limit: agreement among plausible readings is not proof. Two variants
could agree on a wrong-but-plausible age, and nothing here would catch it. What
this rules out is the *silent* case -- a single lucky read being trusted alone.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from app.services.stamp_recovery import recover_age  # noqa: E402


def _reader(by_width: dict[int, str]):
    """Stands in for OCR: maps a crop's width to the age line it returns.

    Width is the crop's *final* width, after any upscale, since that is what a
    recognizer actually sees.
    """

    def read(crop: np.ndarray) -> list[str]:
        return [by_width.get(crop.shape[1], "")]

    return read


def _cell(width: int = 800, height: int = 300) -> np.ndarray:
    return np.full((height, width), 255, dtype=np.uint8)


def test_agreeing_plausible_readings_are_accepted():
    cell = _cell()
    # Widths the variants will produce; the damaged reads are the implausible ones.
    reader = _reader({
        360: "வயது : 59 பாலினம் : ஆண்",
        400: "வயது : 5பாலினம் : ஆண்",
        440: "வயது : 59 பாலினம் : ஆண்",
        480: "வயது : 5பாலினம் : ஆண்",
        520: "வயது : 5பாலினம் : ஆண்",
        560: "வயது : 5பாலினம் : ஆண்",
        800: "வயது : 5பாலினம் : ஆண்",
    })
    assert recover_age(cell, reader) == 59


def test_an_implausible_reading_never_wins_however_often_it_appears():
    """`5` outnumbers `59` five to two on the real cards; it must still lose."""
    cell = _cell()
    reader = _reader({w: "வயது : 5பாலினம்" for w in (360, 400, 440, 480, 520, 560, 800)})
    reader_with_two_good = _reader({
        360: "வயது : 59 பாலினம்",
        440: "வயது : 59 பாலினம்",
        **{w: "வயது : 5பாலினம்" for w in (400, 480, 520, 560, 800)},
    })
    assert recover_age(cell, reader) is None
    assert recover_age(cell, reader_with_two_good) == 59


def test_a_single_plausible_reading_is_not_trusted():
    """One lucky read is the silent-corruption case this exists to prevent."""
    cell = _cell()
    reader = _reader({
        360: "வயது : 59 பாலினம்",
        **{w: "வயது : 5பாலினம்" for w in (400, 440, 480, 520, 560, 800)},
    })
    assert recover_age(cell, reader) is None


def test_disagreeing_plausible_readings_are_refused():
    """Two different plausible ages means we do not know which is right."""
    cell = _cell()
    reader = _reader({
        360: "வயது : 59 பாலினம்",
        440: "வயது : 38 பாலினம்",
        **{w: "வயது : 5பாலினம்" for w in (400, 480, 520, 560, 800)},
    })
    assert recover_age(cell, reader) is None


def test_ages_outside_the_electoral_range_are_not_plausible():
    cell = _cell()
    for bad in ("7", "9", "150", "0"):
        reader = _reader({w: f"வயது : {bad} பாலினம்" for w in
                          (360, 400, 440, 480, 520, 560, 800)})
        assert recover_age(cell, reader) is None, bad


def test_no_age_line_at_all_recovers_nothing():
    assert recover_age(_cell(), _reader({})) is None


def test_the_cell_is_also_re_read_enlarged():
    """Pages render at their native resolution, which here is 143 dpi.

    At that size the recognizer loses digits it can read when the crop is
    enlarged: on the real roll, upscaling recovered 21 of 48 ages that native
    scale could not, against 5 without it. So scale is a variant like the crop
    width -- not a tuned constant, since agreement still decides.
    """
    cell = _cell(width=800)
    # Only the enlarged reads carry the age; every native-width read is damaged.
    by_width = {int(800 * f): "வயது : 5பாலினம் : ஆண்" for f in (0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 1.0)}
    by_width.update({int(800 * f * 2): "வயது : 59 பாலினம் : ஆண்" for f in (0.45, 0.55)})
    assert recover_age(cell, _reader(by_width)) == 59


def test_an_enlarged_misread_still_has_to_agree():
    """Enlarging is not trusted more than anything else."""
    cell = _cell(width=800)
    by_width = {int(800 * f): "வயது : 5பாலினம்" for f in (0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 1.0)}
    by_width[int(800 * 0.45 * 2)] = "வயது : 59 பாலினம்"
    by_width[int(800 * 0.55 * 2)] = "வயது : 38 பாலினம்"
    assert recover_age(cell, _reader(by_width)) is None


# --------------------------------------------------------------- real rolls

fitz = pytest.importorskip("fitz", reason="pymupdf needed to render the rolls")

REPO_ROOT = Path(__file__).resolve().parents[3]
TAM_16 = (
    REPO_ROOT / "PDF" / "Penn PDF"
    / "2026-FC-EROLLGEN-S22-58-SIR-FinalRoll-Revision2-TAM-16-WI (1).pdf"
)
TRUE_AGES = {13: 59, 14: 44, 20: 30}

needs_roll = pytest.mark.skipif(
    not TAM_16.exists(), reason=f"roll not present: {TAM_16.name}"
)


def _real_cell(serial: int, dpi: int = 300) -> np.ndarray:
    import cv2

    doc = fitz.open(TAM_16)
    try:
        pixmap = doc[3].get_pixmap(dpi=dpi)
        image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
            pixmap.height, pixmap.width, pixmap.n
        )
        page = (
            cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
            if pixmap.n >= 3 else image[:, :, 0].copy()
        )
    finally:
        doc.close()
    row, col = (serial - 1) // 3, (serial - 1) % 3
    height, width = page.shape
    cell_h, cell_w = height * 0.90 / 10, width * 0.96 / 3
    top = int(height * 0.055 + cell_h * row)
    left = int(width * 0.02 + cell_w * col)
    return page[top:top + int(cell_h), left:left + int(cell_w)]


def _ocr_reader(crop: np.ndarray) -> list[str]:
    import cv2

    from app.services.ocr_service import run_ocr

    return [line.text for line in run_ocr(cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR)).lines]


@needs_roll
@pytest.mark.parametrize("serial", sorted(TRUE_AGES))
def test_real_stamped_age_is_recovered(serial):
    assert recover_age(_real_cell(serial), _ocr_reader) == TRUE_AGES[serial]


@needs_roll
def test_a_live_elector_card_recovers_its_own_age_unchanged():
    """Safe to run on unstamped cards, since the caller may not know yet."""
    assert recover_age(_real_cell(17), _ocr_reader) == 22

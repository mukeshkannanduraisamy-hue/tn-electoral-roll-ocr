"""The stamp reaches the record only if `parse` looks at the page image.

`_parse_cell` accepts stamp geometry, but nothing sets it unless the parse loop
crops each cell and runs the detector. This is the wiring test: a page carrying
one stamped card and one live card must come back with one of each.

It also pins the mixed-page behaviour. Page 4 of TAM-16 has 15 stamped cards and
15 live ones sharing it, so any page-level shortcut would strike off half the
electors on the page.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from app.schemas.core import BBox, LayoutInfo, OcrLine  # noqa: E402
from app.templates.electoral_roll_ta import ElectoralRollTamilTemplate  # noqa: E402

CELL_W, CELL_H = 560, 220
PAGE_W, PAGE_H = CELL_W, CELL_H * 2


def _line(text: str, x: float, y: float, conf: float = 0.95) -> OcrLine:
    return OcrLine(
        id=f"l{abs(hash((text, x, y))) % 10**8}",
        text=text,
        confidence=conf,
        bbox=BBox(x=x, y=y, w=max(8.0, len(text) * 7.0), h=16.0),
    )


def _card_furniture(page: np.ndarray, top: int) -> None:
    cv2.rectangle(page, (3, top + 3), (CELL_W - 4, top + CELL_H - 4), 0, 2)
    cv2.rectangle(page, (430, top + 40), (530, top + 180), 0, 2)


def _draw_stamp(page: np.ndarray, top: int) -> None:
    layer = np.full((CELL_H * 2, CELL_W * 2), 255, dtype=np.uint8)
    cv2.putText(layer, "DELETED", (60, CELL_H), cv2.FONT_HERSHEY_SIMPLEX,
                2.6, 0, 2, cv2.LINE_AA)
    centre = (layer.shape[1] / 2, layer.shape[0] / 2)
    layer = cv2.warpAffine(layer, cv2.getRotationMatrix2D(centre, 62.0, 1.0),
                           (layer.shape[1], layer.shape[0]), borderValue=255)
    ys, xs = np.where(layer < 128)
    crop = layer[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    crop = cv2.resize(crop, (int(CELL_W * 0.55), int(CELL_H * 0.92)))
    region = page[top + 8:top + 8 + crop.shape[0], 20:20 + crop.shape[1]]
    np.minimum(region, crop, out=region)


def _page_with_one_stamped_card() -> tuple[np.ndarray, list[OcrLine], LayoutInfo]:
    page = np.full((PAGE_H, PAGE_W), 255, dtype=np.uint8)
    _card_furniture(page, 0)
    _card_furniture(page, CELL_H)
    _draw_stamp(page, 0)                      # top card only

    lines = [
        # stamped card, no reason code -- the stamp must carry the verdict alone
        _line("13", 120, 16, 0.999),
        _line("IEB1717636", 400, 16, 0.986),
        _line("பெயர் : சண்முகம்", 20, 45),
        _line("தந்தை பெயர்: காளியப்பன்", 20, 70),
        _line("வீட்டு எண் : 2-2", 20, 95),
        _line("வயது : 59 பாலினம் : ஆண்", 20, 120),
        # live card
        _line("17", 120, CELL_H + 16, 1.0),
        _line("IEB2121796", 400, CELL_H + 16, 0.996),
        _line("பெயர் : பவித்ரா", 20, CELL_H + 45),
        _line("கணவர் பெயர்: செல்வராஜ்", 20, CELL_H + 70),
        _line("வீட்டு எண் : 2/19", 20, CELL_H + 95),
        _line("வயது : 22 பாலினம் : பெண்", 20, CELL_H + 120),
    ]
    layout = LayoutInfo(
        cells=[
            BBox(x=0, y=0, w=CELL_W, h=CELL_H),
            BBox(x=0, y=CELL_H, w=CELL_W, h=CELL_H),
        ],
        rows=2,
        cols=1,
    )
    return page, lines, layout


def _parse_page():
    page, lines, layout = _page_with_one_stamped_card()
    template = ElectoralRollTamilTemplate()
    return template.parse(
        lines, layout, "page-1", (PAGE_W, PAGE_H),
        image=cv2.cvtColor(page, cv2.COLOR_GRAY2BGR),
    )


def test_the_stamped_card_is_marked_deleted_from_the_image_alone():
    records = _parse_page()
    assert len(records) == 2
    assert records[0].fields["is_deleted"].original_value == "Yes"


def test_the_live_card_sharing_the_page_is_left_alone():
    """Half of TAM-16 page 4 is live; a page-level rule would strike them off."""
    records = _parse_page()
    assert records[1].fields["is_deleted"].original_value == "No"


def test_every_record_carries_an_explicit_verdict():
    for record in _parse_page():
        assert record.fields["is_deleted"].original_value in ("Yes", "No")


def test_an_age_the_stamp_destroyed_is_not_left_holding_the_damaged_value():
    """A stamped card whose age line lost a digit must not store the remnant.

    `59` read as `5` is under MIN_AGE. Storing it would be a wrong age; the field
    is left unreadable instead, and recovery fills it when the re-reads agree.
    """
    page, lines, layout = _page_with_one_stamped_card()
    lines = [ln for ln in lines if "வயது : 59" not in ln.text]
    lines.append(_line("வயது : 5பாலினம் : ஆண்", 20, 120, 0.936))

    template = ElectoralRollTamilTemplate()
    records = template.parse(
        lines, layout, "page-1", (PAGE_W, PAGE_H),
        image=cv2.cvtColor(page, cv2.COLOR_GRAY2BGR),
    )
    age = records[0].fields["age"].original_value
    assert age != "5", "stored the digit the stamp left behind as the age"


def test_stamp_fragments_are_dropped_in_a_cell_that_is_not_at_the_origin():
    """Guards a coordinate-space mismatch.

    Stamp geometry is found on a cell crop while OCR boxes are in page
    coordinates. If the two are never reconciled, fragment suppression works only
    for the cell that happens to sit at the page origin -- so this stamps the
    *second* card and plants a fragment in it.
    """
    page = np.full((PAGE_H, PAGE_W), 255, dtype=np.uint8)
    _card_furniture(page, 0)
    _card_furniture(page, CELL_H)
    _draw_stamp(page, CELL_H)                 # bottom card this time

    # The stamped card has no serial line of its own, so the only bare-number
    # candidate is the fragment. Suppressed, the serial stays empty; unsuppressed,
    # stamp ink becomes the elector's serial number.
    lines = [
        _line("17", 120, 16, 1.0),
        _line("IEB2121796", 400, 16, 0.996),
        _line("பெயர் : பவித்ரா", 20, 45),
        _line("வயது : 22 பாலினம் : பெண்", 20, 120),
        _line("IEB1717636", 400, CELL_H + 16, 0.986),
        _line("பெயர் : சண்முகம்", 20, CELL_H + 45),
        _line("வயது : 59 பாலினம் : ஆண்", 20, CELL_H + 120),
        _line("7", 140, CELL_H + 20, 0.945),   # stamp ink read as a number
    ]
    layout = LayoutInfo(
        cells=[
            BBox(x=0, y=0, w=CELL_W, h=CELL_H),
            BBox(x=0, y=CELL_H, w=CELL_W, h=CELL_H),
        ],
        rows=2,
        cols=1,
    )
    template = ElectoralRollTamilTemplate()
    records = template.parse(
        lines, layout, "page-1", (PAGE_W, PAGE_H),
        image=cv2.cvtColor(page, cv2.COLOR_GRAY2BGR),
    )

    assert records[1].fields["is_deleted"].original_value == "Yes"
    assert records[1].fields["serial"].original_value != "7", (
        "stamp ink became the elector's serial number"
    )

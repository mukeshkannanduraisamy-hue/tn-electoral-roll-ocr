"""Template for Tamil Nadu SIR electoral roll pages.

Page anatomy
------------
Header      Assembly constituency no. + name, part number
Body        3 x 10 grid of bordered record cells, 30 voters per page
Footer      Age-qualifying date, publication date, "page N of M"

Each record cell contains::

    +--------------------------------------------------+
    | [ 181 ]                            ZHT0308742     |   serial + EPIC
    | பெயர் : சுசீலா -                    +-----------+  |   name
    | கணவர் பெயர் : சண்முகம் -             |  Photo is |  |   relation
    | வீட்டு எண் : 5-177                   | available |  |   house no.
    | வயது : 34  பாலினம் : பெண்            +-----------+  |   age + gender
    +--------------------------------------------------+

Note the last line carries *two* fields, and the relation label varies by
gender/parentage. Both are handled in `text_utils.segment_labels`.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

import cv2
import numpy as np

from ..config import settings
from ..schemas.core import (
    BBox,
    ColumnDef,
    ColumnType,
    FieldValue,
    Issue,
    IssueCode,
    IssueSeverity,
    LayoutInfo,
    OcrLine,
    Record,
)
from ..services.layout_service import assign_lines_to_cells
from ..services.ocr_service import run_ocr
from ..services.stamp_detector import StampMark, covers, find_stamp_marks
from ..services.stamp_recovery import recover_age
from .deletion_signals import assess_deletion, parse_reason_code
from .field_integrity import house_number_is_intact
from .text_utils import (
    best_enum_match,
    clean_identifier,
    extract_digits,
    normalize,
    segment_labels,
    strip_value,
)

# ---------------------------------------------------------------------------
# Label vocabulary
# ---------------------------------------------------------------------------

# Multiple spellings per key: the printed form varies between districts and
# OCR reliably drops the odd vowel sign, so variants earn their keep.
LABELS: dict[str, list[str]] = {
    "relation_husband": [
        "கணவர் பெயர்", "கணவரின் பெயர்", "கணவர்பெயர்", "கணவர்",
        "கணவா பெயர்", "கணவா் பெயர்", "கணவர் பெயர்:", "கணவரின் பெயா",
        "கணவா்பெயர்", "கணவா் பெயா", "கணவா்", "கனவர் பெயர்",
        "கனவர்பெயர்", "கனவர்", "கணவா பெயா", "கணவர்பெயா",
        "Husband", "Husband Name", "Husband's Name", "Husband:"
    ],
    "relation_father": [
        "தந்தையின் பெயர்", "தந்தை பெயர்", "தந்தையின்பெயர்", "தந்தையின்",
        "தநதையின் பெயர்", "தந்தையின் பெயா", "தந்தை பெயா", "தந்தையின் பெயர்:",
        "தநதையின்பெயர்", "தந்தை பெயர்:", "தநதை பெயர்", "தநதையின்",
        "தந்தையன் பெயர்", "தந்தையின் பெயா்", "தந்தையிள் பெயர்",
        "Father", "Father Name", "Father's Name", "Father:"
    ],
    "relation_mother": [
        "தாயின் பெயர்", "தாய் பெயர்", "தாயின்பெயர்", "தாயின்",
        "தாயின் பெயா", "தாய் பெயா", "தாயின் பெயர்:",
        "தாயிள் பெயர்", "தாயின்பெயா", "தாய்பெயர்", "தாய்",
        "Mother", "Mother Name", "Mother's Name", "Mother:"
    ],
    "relation_other": [
        "குடும்பத் தலைவர் பெயர்", "குடும்ப தலைவர் பெயர்", "குடும்ப பெயர்", "குடும்பத் தலைவர்",
        "குடும்ப தலைவர்", "குடும்பத் தலைவி", "குடும்ப", "குடும்ப பெயர்:",
        "பாதுகாவலர் பெயர்", "பாதுகாவலர்", "காப்பாளர் பெயர்", "காப்பாளர்",
        "உறவினர் பெயர்", "உறவினர்", "உறவு முறை", "உறவு பெயர்", "உறவு",
        "மற்றவை பெயர்", "இதர பெயர்", "மற்றவை பெயா", "இதர பெயா",
        "Family", "Family Name", "Family:", "Guardian", "Guardian Name", "Guardian:",
        "Relative", "Relative Name", "Relation", "Relation Name", "Relation:"
    ],
    "house_number": [
        "வீட்டு எண்", "வீட்டுஎண்", "வீடு எண்", "வீட்டு எஸ்",
        "வீட்டு என", "வீட்டு எண", "வீட்டு எண்:", "வீட்டுஎண",
        "வீட்டுஎண்:", "வீட்டு எண் :", "வீட்டுஎன்", "வீட்டு எள்",
        "வீட்டு என்", "வீட்டு எண்.", "வீட்டு எர்",
        "House No", "House No.", "House Number", "House:"
    ],
    "age": [
        "வயது", "வயது:", "வயது -", "வயது :", "வயது.", "வய து",
        "வயதூ", "வயதி", "வயத", "Age", "Age:"
    ],
    "gender": [
        "பாலினம்", "பாலினம", "பாலினம்:", "பாலினம:", "பாலிளம்",
        "பாலினம் :", "பாலிணம்", "பாலனம்", "பாலினம் -",
        "Gender", "Gender:"
    ],
    # Generic name label MUST be matched last -- it is a substring of every
    # relation label above. `RELATION_KEYS` is passed as the priority set so
    # a relation always wins an overlapping match.
    "name": [
        "பெயர்", "பெயா", "பெயா்", "பெயர்:", "பெயா:", "Name", "Name:"
    ],
}

RELATION_KEYS = [
    "relation_husband",
    "relation_father",
    "relation_mother",
    "relation_other",
]

RELATION_TYPE_LABEL = {
    "relation_husband": "Husband",
    "relation_father": "Father",
    "relation_mother": "Mother",
    "relation_other": "Other",
}

GENDER_OPTIONS = {
    "Male": "ஆண்",
    "Female": "பெண்",
    "Other": "மற்றவை",
}

# Permissive on extraction, strict on validation (see `validate`).
EPIC_PERMISSIVE_RE = re.compile(r"^[A-Z]{2,4}\d{6,9}$")
EPIC_CANONICAL_RE = re.compile(r"^[A-Z]{3}\d{7}$")

# A deletion reason code sitting alone in the serial box, which is how these
# rolls print it. Matched before the serial patterns so `S2` is not read as 2.
STANDALONE_CODE_RE = re.compile(r"^([SERMQWsermqw]\d?)$")

# Serial with the code run together, for rolls that print them in one line. The
# optional trailing digit is `S2` on serial 25, whose meaning is undocumented.
SERIAL_WITH_CODE_RE = re.compile(
    r"^\s*\[?\s*([SERMQWsermqw]\d?)?\s*[\.\-:\s]*(\d{1,4})\s*\]?\s*"
)
SERIAL_BARE_RE = re.compile(
    r"^\s*\[?\s*([SERMQWsermqw]\d?)?\s*[\.\-:\s]*(\d{1,4})\s*\]?\s*$"
)

# Placeholder text printed where a photo would be -- never a field value.
PHOTO_NOISE = (
    "photo",
    "available",
    "not available",
    "புகைப்படம",
    "புகைப்படம்",
    "இல்லை",
    "இருக்கிறது",
    "கிடைக்கும்",
    "இருக்கும்",
)

MIN_AGE = 18
MAX_AGE = 120


class ElectoralRollTamilTemplate:
    id = "electoral_roll_ta"
    name = "Electoral Roll (Tamil)"
    description = (
        "Tamil Nadu SIR / EROLLGEN voter roll pages: 30 records per page in a "
        "3x10 grid, with serial number, EPIC ID, name, relation, house number, "
        "age and gender."
    )
    languages = ["ta", "en"]

    # ------------------------------------------------------------- metadata

    def columns(self) -> list[ColumnDef]:
        return [
            ColumnDef(key="serial", label="வரிசை எண் (S.No)", type=ColumnType.NUMBER, width=90,
                      required=True, description="Serial number within the part"),
            ColumnDef(key="epic", label="அடையாள அட்டை எண் (EPIC ID)", type=ColumnType.IDENTIFIER, width=160,
                      required=True, description="Elector Photo Identity Card number"),
            ColumnDef(key="name", label="பெயர் (Name)", type=ColumnType.TEXT, width=200,
                      required=True),
            ColumnDef(key="relation_type", label="உறவு முறை (Relation)", type=ColumnType.ENUM, width=130,
                      enum_values=list(RELATION_TYPE_LABEL.values())),
            ColumnDef(key="relation_name", label="உறவினரின் பெயர் (Relation Name)", type=ColumnType.TEXT,
                      width=220, required=True),
            ColumnDef(key="house_number", label="வீட்டு எண் (House No)", type=ColumnType.TEXT, width=120,
                      required=True),
            ColumnDef(key="age", label="வயது (Age)", type=ColumnType.NUMBER, width=80, required=True),
            ColumnDef(key="gender", label="பாலினம் (Gender)", type=ColumnType.ENUM, width=100,
                      required=True, enum_values=list(GENDER_OPTIONS.keys())),
            ColumnDef(key="is_deleted", label="நீக்கப்பட்டது (Deleted)", type=ColumnType.TEXT, width=110,
                      description="Whether elector record is deleted or shifted"),
            ColumnDef(key="deletion_reason", label="நீக்க காரணம் (Deletion Reason)", type=ColumnType.TEXT, width=180,
                      description="Reason code: S - Shifted, E - Expired, R - Repeated, M - Missing, Q - Disqualified, DELETED"),
            ColumnDef(key="deletion_signals", label="நீக்க ஆதாரம் (Deletion Signals)", type=ColumnType.TEXT, width=150,
                      description="Which readers marked this elector deleted: reason_code, stamp, or both. "
                                  "Either alone is sufficient, so this is how a disagreement is found later"),
            ColumnDef(key="section_name", label="பிரிவு பெயர் (Section Name)", type=ColumnType.TEXT, width=240,
                      description="Section number and name"),
            ColumnDef(key="part_number", label="பாகம் எண் (Part No)", type=ColumnType.NUMBER, width=90,
                      description="Part number"),
            ColumnDef(key="list_type", label="பட்டியல் வகை (List Type)", type=ColumnType.TEXT, width=140,
                      description="Main Roll / Additions / Deletions / Modifications"),
        ]

    def expected_grid(self) -> tuple[int, int] | None:
        return (settings.expected_grid_rows, settings.expected_grid_cols)

    def consensus_fields(self) -> list[str]:
        """Free-text proper nouns eligible for cross-corpus spelling consensus.

        Only these. Numbers and identifiers must never be "corrected" by
        majority vote -- every EPIC is unique by definition, and harmonising
        them would destroy data rather than repair it.
        """
        return ["name", "relation_name"]

    # ------------------------------------------------------------- detection

    def detect(self, lines: list[OcrLine], page_size: tuple[int, int]) -> float:
        """Score how strongly this page looks like a Tamil electoral roll."""
        if not lines:
            return 0.0

        blob = normalize(" ".join(ln.text for ln in lines))
        if not blob:
            return 0.0

        signals = 0.0

        # Tamil field labels are the strongest signal.
        anchors = ["பெயர்", "வயது", "பாலினம்", "வீட்டு"]
        hits = sum(1 for a in anchors if a in blob)
        signals += 0.55 * (hits / len(anchors))

        # A page full of EPIC-shaped identifiers is near-conclusive.
        epic_like = sum(
            1 for ln in lines if EPIC_PERMISSIVE_RE.match(clean_identifier(ln.text))
        )
        if epic_like >= 10:
            signals += 0.35
        elif epic_like >= 3:
            signals += 0.20

        # Roll-specific header vocabulary.
        if "சட்டமன்ற" in blob or "தொகுதி" in blob or "பாகம்" in blob:
            signals += 0.10

        return min(1.0, signals)

    @staticmethod
    def _extract_header_metadata(lines: list[OcrLine]) -> dict[str, Any]:
        meta = {
            "part_number": "",
            "section_name": "",
            "list_type": "",
            "is_deletions_page": False,
        }
        full_text = " ".join(ln.text for ln in lines)

        # 1. Part Number
        m_part = re.search(r"பாகம்\s*எண்\s*[:\-]?\s*(\d+)", full_text, re.IGNORECASE)
        if not m_part:
            m_part = re.search(r"Part\s*No\.?\s*[:\-]?\s*(\d+)", full_text, re.IGNORECASE)
        if m_part:
            meta["part_number"] = m_part.group(1)

        # 2. Section Name
        m_sec = re.search(r"பிரிவு\s*எண்\s*(?:மற்றும்\s*பெயர்)?\s*[:\-]?\s*([^\n\r]+)", full_text)
        if m_sec:
            sec_val = m_sec.group(1).strip()
            sec_val = re.sub(r"\s*பாகம்.*$", "", sec_val)
            meta["section_name"] = sec_val.strip()

        # 3. List Type / Supplement Title
        if "நீக்கல் பட்டியல்" in full_text or "நீக்கல்" in full_text[:400]:
            meta["list_type"] = "Deletions List (நீக்கல் பட்டியல்)"
            meta["is_deletions_page"] = True
        elif "சேர்த்தல் பட்டியல்" in full_text or "சேர்த்தல்" in full_text[:400]:
            meta["list_type"] = "Additions List (சேர்த்தல் பட்டியல்)"
        elif "திருத்தப் பட்டியல்" in full_text or "திருத்தப்" in full_text[:400]:
            meta["list_type"] = "Modifications List (திருத்தப் பட்டியல்)"

        return meta

    # ---------------------------------------------------------------- parse

    def parse(
        self,
        lines: list[OcrLine],
        layout: LayoutInfo,
        page_id: str,
        page_size: tuple[int, int],
        image: np.ndarray | None = None,
    ) -> list[Record]:
        cells = layout.cells or []
        header_meta = self._extract_header_metadata(lines)

        buckets = assign_lines_to_cells(
            lines,
            cells,
            rows=layout.rows or settings.expected_grid_rows,
            cols=layout.cols or settings.expected_grid_cols,
        )

        records: list[Record] = []
        for index, cell in enumerate(cells):
            cell_lines = sorted(
                buckets.get(index, []),
                key=lambda ln: (round(ln.bbox.cy / 8), ln.bbox.cx),
            )

            if not cell_lines and image is None:
                continue

            # The stamp has to be found in the pixels: it sits at 55-68 degrees
            # and OCR never returns a line matching it, only fragments.
            stamp_marks = self._find_cell_stamp(image, cell)

            record = self._parse_cell(
                cell_lines, cell, index, page_id, header_meta, stamp_marks
            )

            has_name = bool(record.fields.get("name") and record.fields["name"].original_value.strip())
            has_house = bool(record.fields.get("house_number") and record.fields["house_number"].original_value.strip())
            has_rel = bool(record.fields.get("relation_name") and record.fields["relation_name"].original_value.strip())
            is_deleted_cell = bool(record.fields.get("is_deleted") and record.fields["is_deleted"].original_value == "Yes")

            # Crop OCR Recovery pass when fields are missing or cell is marked deleted/shifted
            if image is not None and (not has_name or not has_house or not has_rel or is_deleted_cell):
                try:
                    x1, y1 = max(0, int(cell.x)), max(0, int(cell.y))
                    x2, y2 = min(image.shape[1], int(cell.x + cell.w)), min(image.shape[0], int(cell.y + cell.h))
                    if x2 - x1 > 20 and y2 - y1 > 20:
                        cell_crop = image[y1:y2, x1:x2].copy()
                        gray = cv2.cvtColor(cell_crop, cv2.COLOR_BGR2GRAY) if cell_crop.ndim == 3 else cell_crop
                        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
                        enhanced = clahe.apply(gray)
                        enhanced_bgr = cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)
                        resized_crop = cv2.resize(enhanced_bgr, (0, 0), fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)

                        ocr_res = run_ocr(resized_crop)
                        if ocr_res and ocr_res.lines:
                            recovered_record = self._parse_cell(ocr_res.lines, cell, index, page_id, header_meta)
                            for f_key in ("name", "relation_type", "relation_name", "house_number", "age", "gender", "epic", "is_deleted", "deletion_reason"):
                                rec_val = recovered_record.fields.get(f_key)
                                orig_val = record.fields.get(f_key)
                                if rec_val and rec_val.original_value and (not orig_val or not orig_val.original_value or f_key in ("name", "house_number", "relation_name")):
                                    record.fields[f_key] = rec_val
                except Exception:
                    pass

            # The stamp costs the age line a digit -- `59` is read as `5`, under
            # the electoral minimum. The remnant must never be stored as an age,
            # and re-reading the same crop cannot help, so recovery gets a go.
            if stamp_marks and image is not None:
                self._recover_stamped_age(record, image, cell)

            # Re-judge the house number now the crop re-OCR has had its say: it
            # overwrites the value either way, so the first read's verdict may be
            # attached to a value that no longer exists.
            self._flag_suspect_house_number(record, stamped=bool(stamp_marks))

            voter_keys = ("serial", "epic", "name", "relation_name", "house_number", "age", "gender")
            if not any(record.fields.get(k) and record.fields[k].original_value.strip() for k in voter_keys):
                continue

            records.append(record)
        return records

    _HOUSE_STAMP_WARNING = "may have lost a separator to the DELETED stamp"

    @classmethod
    def _flag_suspect_house_number(cls, record: Record, stamped: bool) -> None:
        """Mark a house number the stamp may have flattened, or withdraw the mark.

        Idempotent, because it runs twice: once on the first read and again after
        the crop re-OCR, which overwrites `house_number` unconditionally. On real
        pages that overwrite went both ways -- it repaired `22` into `2-2` on one
        card and broke `2-19` into `219` on another -- so a verdict from the first
        read alone is attached to a value that no longer exists.

        The value is never corrected. `22` cannot be told from a genuine `22`;
        only a human looking at the page image can settle it.
        """
        record.issues = [
            issue
            for issue in record.issues
            if cls._HOUSE_STAMP_WARNING not in (issue.message or "")
        ]
        if not stamped:
            return

        field = record.fields.get("house_number")
        value = (field.edited_value or field.original_value or "").strip() if field else ""
        if not value or house_number_is_intact(value):
            return

        record.issues.append(
            Issue(
                code=IssueCode.BAD_FORMAT,
                severity=IssueSeverity.WARNING,
                field="house_number",
                message=(
                    f"'{value}' {cls._HOUSE_STAMP_WARNING} "
                    f"(e.g. '2-2' read as '22'); check the page image"
                ),
            )
        )

    @staticmethod
    def _recover_stamped_age(record: Record, image: np.ndarray, cell: BBox) -> None:
        """Replace an age the stamp destroyed, or leave the field unreadable.

        A stored age that is wrong is worse than one that is missing, so the
        damaged remnant is cleared whether or not recovery then succeeds.
        """
        field = record.fields.get("age")
        if field is None:
            return

        digits = extract_digits(field.original_value or "")
        if digits:
            try:
                if MIN_AGE <= int(digits) <= MAX_AGE:
                    return                      # came through the stamp intact
            except ValueError:
                pass

        field.original_value = ""
        field.confidence = 0.0

        x1, y1 = max(0, int(cell.x)), max(0, int(cell.y))
        x2 = min(image.shape[1], int(cell.x + cell.w))
        y2 = min(image.shape[0], int(cell.y + cell.h))
        if x2 - x1 <= 20 or y2 - y1 <= 20:
            return
        crop = image[y1:y2, x1:x2]
        if crop.ndim == 3:
            crop = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

        def read(variant: np.ndarray) -> list[str]:
            result = run_ocr(cv2.cvtColor(variant, cv2.COLOR_GRAY2BGR))
            return [line.text for line in result.lines]

        try:
            recovered = recover_age(crop, read)
        except Exception:
            return
        if recovered is not None:
            field.original_value = str(recovered)
            field.confidence = 1.0

    @staticmethod
    def _find_cell_stamp(
        image: np.ndarray | None, cell: BBox
    ) -> list[StampMark]:
        """Stamp geometry for one cell, translated into *page* coordinates.

        The detector works on a crop and so reports cell-local pixels, but every
        OCR box it is compared against is page-space. Returning cell-local marks
        would leave fragment suppression working only for whichever cell happens
        to sit at the page origin.

        Returns nothing when there is no page image to look at, which leaves the
        reason code as the only signal -- correct, since a cell with no pixels
        offers no evidence either way.
        """
        if image is None:
            return []
        x1, y1 = max(0, int(cell.x)), max(0, int(cell.y))
        x2 = min(image.shape[1], int(cell.x + cell.w))
        y2 = min(image.shape[0], int(cell.y + cell.h))
        if x2 - x1 <= 20 or y2 - y1 <= 20:
            return []
        crop = image[y1:y2, x1:x2]
        if crop.ndim == 3:
            crop = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        try:
            marks = find_stamp_marks(crop)
        except cv2.error:
            # A malformed crop must not lose the whole page; the reason code
            # still carries the verdict.
            return []
        return [
            StampMark(
                x=mark.x + x1,
                y=mark.y + y1,
                w=mark.w,
                h=mark.h,
                angle=mark.angle,
            )
            for mark in marks
        ]

    def _parse_cell(
        self,
        lines: list[OcrLine],
        cell: BBox,
        index: int,
        page_id: str,
        header_meta: dict[str, Any] | None = None,
        stamp_marks: list[StampMark] | None = None,
    ) -> Record:
        header_meta = header_meta or {}
        stamp_marks = stamp_marks or []
        record = Record(
            id=uuid.uuid4().hex[:12],
            page_id=page_id,
            index=index,
            template_id=self.id,
            bbox=cell,
        )

        if not lines:
            record.issues.append(
                Issue(
                    code=IssueCode.OCR_EMPTY,
                    severity=IssueSeverity.ERROR,
                    message="No text recognised in this cell",
                )
            )
            for col in self.columns():
                record.fields[col.key] = FieldValue(key=col.key)
            return record

        # Stamp ink that OCR recognised as text -- a stray `C` at 0.945 is the
        # outline of the `D`. High confidence, so nothing downstream would doubt
        # it; drop it before any of it is mistaken for a field value.
        if stamp_marks:
            lines = [
                ln
                for ln in lines
                if not any(
                    covers(mark, (ln.bbox.x, ln.bbox.y, ln.bbox.w, ln.bbox.h))
                    for mark in stamp_marks
                )
            ]
            if not lines:
                for col in self.columns():
                    record.fields[col.key] = FieldValue(key=col.key)
                return record

        consumed: set[str] = set()
        values: dict[str, tuple[str, float, BBox | None, list[str]]] = {}

        # Deletion signals. The stamp arrives as geometry from the image because
        # OCR never returns it as a line; the reason code is read below, out of
        # the serial box, and recorded even when the two disagree.
        reason_code: str | None = None
        stamp_found = bool(stamp_marks)
        for ln in lines:
            if any(
                term in ln.text.upper()
                for term in ("DELETED", "நீக்கப்பட்டது", "CANCELLED")
            ):
                stamp_found = True
                break

        def put(key: str, value: str, line: OcrLine) -> None:
            """Record a field value, keeping the first (topmost) hit."""
            if not value or key in values:
                return
            values[key] = (value, line.confidence, line.bbox, [line.id])

        # --- pass 1: serial + EPIC, identified by shape and position -------
        top_band = cell.y + cell.h * 0.45
        for idx_line, line in enumerate(lines):
            text = normalize(line.text)
            if line.bbox.cy > top_band:
                continue

            # The reason code is usually printed on its own, left of the serial.
            # It has to be claimed before the serial patterns see it: `S2` run
            # through them yields serial 2, silently renumbering the elector.
            standalone_code = STANDALONE_CODE_RE.match(text.strip())
            if standalone_code:
                reason_code = standalone_code.group(1).upper()
                consumed.add(line.id)
                continue

            code_prefix = parse_reason_code(text) or ""

            ident = clean_identifier(text)
            if EPIC_PERMISSIVE_RE.match(ident) and "epic" not in values:
                put("epic", ident, line)
                consumed.add(line.id)
                if "serial" not in values:
                    m_ser = SERIAL_WITH_CODE_RE.match(text)
                    if m_ser:
                        put("serial", m_ser.group(2), line)
                continue

            m_ser_bare = SERIAL_BARE_RE.match(text)
            if m_ser_bare:
                if "serial" not in values:
                    put("serial", m_ser_bare.group(2), line)
                    consumed.add(line.id)

            reason_code = reason_code or code_prefix or None

        def _is_noise(text: str) -> bool:
            lowered = text.lower()
            return any(noise in lowered for noise in PHOTO_NOISE)

        def _continuation_value(index: int) -> tuple[str, OcrLine] | None:
            """Value that wrapped onto the following line.

            OCR sometimes breaks a field between the label and its value, so
            the cell reads:

                தந்தையின் பெயர்:
                கடமடைமுனியப்பன் -

            The label line then yields an empty value and the value line
            carries no label, so both are discarded and the field is lost.
            Adopt the next line when it is plain text with no label of its
            own -- otherwise leave it for its own iteration.
            """
            if index + 1 >= len(lines):
                return None
            nxt = lines[index + 1]
            if nxt.id in consumed:
                return None
            nxt_text = normalize(nxt.text)
            if not nxt_text or _is_noise(nxt_text):
                return None
            if segment_labels(
                nxt_text, LABELS,
                threshold=settings.label_fuzzy_threshold,
                priority=RELATION_KEYS,
            ):
                return None
            # A bare identifier or serial belongs to the header, not here.
            if EPIC_PERMISSIVE_RE.match(clean_identifier(nxt_text)):
                return None
            value = strip_value(nxt_text)
            return (value, nxt) if value else None

        # --- pass 2: labelled fields ---------------------------------------
        for line_index, line in enumerate(lines):
            if line.id in consumed:
                continue
            text = normalize(line.text)
            if _is_noise(text):
                continue

            pairs = segment_labels(
                text,
                LABELS,
                threshold=settings.label_fuzzy_threshold,
                priority=RELATION_KEYS,
            )
            if not pairs:
                continue

            for pair_index, (match, raw_value) in enumerate(pairs):
                key = match.key
                value = strip_value(raw_value)
                source = line

                # Only the last label on a line can wrap; an earlier one is
                # bounded by the next label, so an empty value there is a
                # genuine blank rather than a line break.
                if not value and pair_index == len(pairs) - 1:
                    carried = _continuation_value(line_index)
                    if carried:
                        value, source = carried
                        consumed.add(source.id)

                if not value:
                    continue

                # Attribute confidence and geometry to whichever line the
                # value actually came from -- `line` for the normal case,
                # the following line when the value wrapped.
                if key in RELATION_KEYS:
                    put("relation_name", value, source)
                    if "relation_type" not in values:
                        values["relation_type"] = (
                            RELATION_TYPE_LABEL[key],
                            source.confidence,
                            source.bbox,
                            [source.id],
                        )
                elif key == "age":
                    digits = extract_digits(value)
                    if digits:
                        put("age", digits[:3], source)
                elif key == "gender":
                    canonical = best_enum_match(value, GENDER_OPTIONS)
                    put("gender", canonical or value, source)
                elif key == "house_number":
                    put("house_number", value, source)
                elif key == "name":
                    put("name", value, source)
                consumed.add(line.id)

        # --- pass 3: leftovers become an audit trail ------------------------
        unparsed = [
            normalize(ln.text)
            for ln in lines
            if ln.id not in consumed
            and not any(noise in normalize(ln.text).lower() for noise in PHOTO_NOISE)
        ]

        # --- populate metadata & deletion status ---
        # Written on every cell, `"No"` included. Writing only on `"Yes"` left an
        # evaluated live elector indistinguishable from a cell nothing had looked
        # at -- the state all 632 records in the historical database are in.
        verdict = assess_deletion(
            reason_code=reason_code,
            stamp_found=stamp_found,
            on_deletions_page=bool(header_meta.get("is_deletions_page")),
        )
        values["is_deleted"] = (verdict.flag, 1.0, None, [])
        if verdict.reason:
            values["deletion_reason"] = (verdict.reason, 1.0, None, [])
        # Which readers fired, kept because either one alone is enough to strike
        # an elector off. Without it a wrong reading is indistinguishable from a
        # real deletion, and the two signals cannot be reconciled after the fact.
        if verdict.signals:
            values["deletion_signals"] = ("+".join(verdict.signals), 1.0, None, [])

        if header_meta.get("section_name"):
            values["section_name"] = (header_meta.get("section_name"), 1.0, None, [])
        if header_meta.get("part_number"):
            values["part_number"] = (header_meta.get("part_number"), 1.0, None, [])
        if header_meta.get("list_type"):
            values["list_type"] = (header_meta.get("list_type"), 1.0, None, [])

        # --- assemble -------------------------------------------------------
        for col in self.columns():
            if col.key in values:
                value, confidence, bbox, source_ids = values[col.key]
                record.fields[col.key] = FieldValue(
                    key=col.key,
                    original_value=value,
                    confidence=confidence,
                    bbox=bbox,
                    source_line_ids=source_ids,
                )
            else:
                record.fields[col.key] = FieldValue(key=col.key)

        self._flag_suspect_house_number(record, stamped=bool(stamp_marks))

        if unparsed:
            record.issues.append(
                Issue(
                    code=IssueCode.UNPARSED_TEXT,
                    severity=IssueSeverity.INFO,
                    message="Unmatched text in cell: " + " | ".join(unparsed[:4]),
                )
            )

        return record

    # ------------------------------------------------------------- validate

    def validate(self, records: list[Record]) -> None:
        """Attach issues in place. Errors drive the review queue."""
        seen_epics: dict[str, int] = {}

        for record in records:
            fields = record.fields

            # -- required fields --------------------------------------------
            for col in self.columns():
                field = fields.get(col.key)
                if field is None:
                    continue
                if col.required and not field.value.strip():
                    field.issues.append(
                        Issue(
                            code=IssueCode.MISSING_REQUIRED,
                            severity=IssueSeverity.ERROR,
                            message=f"{col.label} is missing",
                            field=col.key,
                        )
                    )

            # -- EPIC format -------------------------------------------------
            epic = fields.get("epic")
            if epic and epic.value:
                cleaned = clean_identifier(epic.value)
                if not EPIC_PERMISSIVE_RE.match(cleaned):
                    epic.issues.append(
                        Issue(
                            code=IssueCode.BAD_FORMAT,
                            severity=IssueSeverity.ERROR,
                            message="EPIC does not look like an identifier "
                                    "(expected 2-4 letters followed by 6-9 digits)",
                            field="epic",
                        )
                    )
                elif not EPIC_CANONICAL_RE.match(cleaned):
                    epic.issues.append(
                        Issue(
                            code=IssueCode.BAD_FORMAT,
                            severity=IssueSeverity.WARNING,
                            message="EPIC is not in the canonical AAA1234567 form",
                            field="epic",
                        )
                    )
                if cleaned in seen_epics:
                    epic.issues.append(
                        Issue(
                            code=IssueCode.DUPLICATE_IDENTIFIER,
                            severity=IssueSeverity.ERROR,
                            message=f"Duplicate EPIC (also on record #{seen_epics[cleaned] + 1})",
                            field="epic",
                        )
                    )
                else:
                    seen_epics[cleaned] = record.index

            # -- age ---------------------------------------------------------
            age = fields.get("age")
            if age and age.value:
                digits = extract_digits(age.value)
                if not digits:
                    age.issues.append(
                        Issue(code=IssueCode.BAD_FORMAT, severity=IssueSeverity.ERROR,
                              message="Age is not numeric", field="age")
                    )
                else:
                    n = int(digits)
                    if not MIN_AGE <= n <= MAX_AGE:
                        age.issues.append(
                            Issue(
                                code=IssueCode.OUT_OF_RANGE,
                                severity=IssueSeverity.ERROR,
                                message=f"Age {n} outside plausible range "
                                        f"{MIN_AGE}-{MAX_AGE}",
                                field="age",
                            )
                        )

            # -- gender ------------------------------------------------------
            gender = fields.get("gender")
            if gender and gender.value and gender.value not in GENDER_OPTIONS:
                gender.issues.append(
                    Issue(
                        code=IssueCode.NOT_IN_ENUM,
                        severity=IssueSeverity.ERROR,
                        message=f"Gender '{gender.value}' is not one of "
                                f"{', '.join(GENDER_OPTIONS)}",
                        field="gender",
                    )
                )

            # -- serial ------------------------------------------------------
            serial = fields.get("serial")
            if serial and serial.value and not serial.value.isdigit():
                serial.issues.append(
                    Issue(code=IssueCode.BAD_FORMAT, severity=IssueSeverity.ERROR,
                          message="Serial number is not numeric", field="serial")
                )

            # -- low confidence ----------------------------------------------
            for field in fields.values():
                if field.original_value and field.confidence < 0.60:
                    field.issues.append(
                        Issue(
                            code=IssueCode.LOW_CONFIDENCE,
                            severity=IssueSeverity.WARNING,
                            message=f"Low OCR confidence ({field.confidence:.0%})",
                            field=field.key,
                        )
                    )

        self._validate_serial_sequence(records)

    @staticmethod
    def _validate_serial_sequence(records: list[Record]) -> None:
        """Serials run consecutively down the page; a gap means a misread.

        This is the highest-value check in the whole template: it catches
        digit errors that are individually plausible (`181` read as `18`)
        and would otherwise sail through every format rule.
        """
        numbered = [
            (r, int(r.fields["serial"].value))
            for r in records
            if r.fields.get("serial") and r.fields["serial"].value.isdigit()
        ]
        if len(numbered) < 3:
            return

        for (prev, prev_n), (curr, curr_n) in zip(numbered, numbered[1:]):
            if curr_n != prev_n + 1:
                curr.fields["serial"].issues.append(
                    Issue(
                        code=IssueCode.NON_SEQUENTIAL_SERIAL,
                        severity=IssueSeverity.WARNING,
                        message=f"Serial {curr_n} does not follow {prev_n}",
                        field="serial",
                    )
                )


TEMPLATE = ElectoralRollTamilTemplate()

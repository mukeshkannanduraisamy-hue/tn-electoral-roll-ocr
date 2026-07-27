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
    "relation_husband": ["கணவர் பெயர்", "கணவரின் பெயர்", "கணவர்பெயர்", "கணவர்"],
    "relation_father": ["தந்தையின் பெயர்", "தந்தை பெயர்", "தந்தையின்பெயர்", "தந்தையின்"],
    "relation_mother": ["தாயின் பெயர்", "தாய் பெயர்", "தாயின்பெயர்", "தாயின்"],
    "relation_other": ["மற்றவை பெயர்", "இதர பெயர்"],
    "house_number": ["வீட்டு எண்", "வீட்டுஎண்", "வீடு எண்", "வீட்டு எஸ்"],
    "age": ["வயது"],
    "gender": ["பாலினம்", "பாலினம"],
    # Generic name label MUST be matched last -- it is a substring of every
    # relation label above. `RELATION_KEYS` is passed as the priority set so
    # a relation always wins an overlapping match.
    "name": ["பெயர்"],
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

    # ---------------------------------------------------------------- parse

    def parse(
        self,
        lines: list[OcrLine],
        layout: LayoutInfo,
        page_id: str,
        page_size: tuple[int, int],
    ) -> list[Record]:
        cells = layout.cells or []
        buckets = assign_lines_to_cells(lines, cells)

        records: list[Record] = []
        for index, cell in enumerate(cells):
            cell_lines = sorted(
                buckets.get(index, []),
                key=lambda ln: (round(ln.bbox.cy / 8), ln.bbox.cx),
            )

            # A cell with no ink is genuinely empty, not a failed read. The
            # last page of a section is routinely part-full (10_16.pdf has
            # two voters on a 30-slot page), and emitting 28 blank records
            # for it would bury the real ones under phantom errors.
            if not cell_lines:
                continue

            record = self._parse_cell(cell_lines, cell, index, page_id)

            # Lines were present but nothing parsed out of them -- e.g. only
            # the "Photo is / available" placeholder. Also not a record.
            if not any(f.original_value.strip() for f in record.fields.values()):
                continue

            records.append(record)
        return records

    def _parse_cell(
        self, lines: list[OcrLine], cell: BBox, index: int, page_id: str
    ) -> Record:
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

        consumed: set[str] = set()
        values: dict[str, tuple[str, float, BBox | None, list[str]]] = {}

        def put(key: str, value: str, line: OcrLine) -> None:
            """Record a field value, keeping the first (topmost) hit."""
            if not value or key in values:
                return
            values[key] = (value, line.confidence, line.bbox, [line.id])

        # --- pass 1: serial + EPIC, identified by shape and position -------
        top_band = cell.y + cell.h * 0.35
        for line in lines:
            text = normalize(line.text)
            if line.bbox.cy > top_band:
                continue

            ident = clean_identifier(text)
            if EPIC_PERMISSIVE_RE.match(ident) and "epic" not in values:
                put("epic", ident, line)
                consumed.add(line.id)
                continue

            digits = extract_digits(text)
            # A bare 1-4 digit number in the top band is the serial.
            if digits and digits == re.sub(r"\D", "", text) and 1 <= len(digits) <= 4:
                if "serial" not in values:
                    put("serial", digits, line)
                    consumed.add(line.id)

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

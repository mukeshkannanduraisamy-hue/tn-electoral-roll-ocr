"""Wire contract shared between the OCR backend and the web client.

These Pydantic models are the single source of truth; `packages/shared-types`
mirrors them in TypeScript. Keep the two in sync -- `scripts/gen-types.ps1`
regenerates the TS side from this module's JSON schema.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------


class BBox(BaseModel):
    """Axis-aligned box in *rendered page image* pixel coordinates."""

    x: float
    y: float
    w: float
    h: float

    @property
    def x2(self) -> float:
        return self.x + self.w

    @property
    def y2(self) -> float:
        return self.y + self.h

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    def contains_point(self, px: float, py: float) -> bool:
        return self.x <= px <= self.x2 and self.y <= py <= self.y2

    def iou(self, other: "BBox") -> float:
        ix = max(0.0, min(self.x2, other.x2) - max(self.x, other.x))
        iy = max(0.0, min(self.y2, other.y2) - max(self.y, other.y))
        inter = ix * iy
        union = self.w * self.h + other.w * other.h - inter
        return inter / union if union > 0 else 0.0


# ---------------------------------------------------------------------------
# Raw OCR output (immutable)
# ---------------------------------------------------------------------------


class OcrLine(BaseModel):
    """One text line as returned by PaddleOCR. Never edited by the user."""

    id: str
    text: str
    confidence: float = Field(ge=0.0, le=1.0)
    bbox: BBox
    polygon: list[tuple[float, float]] = Field(default_factory=list)
    cell_index: int | None = None
    """Index of the layout cell this line was assigned to, if any."""


# ---------------------------------------------------------------------------
# Validation issues
# ---------------------------------------------------------------------------


class IssueSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class IssueCode(str, Enum):
    # Field-level
    MISSING_REQUIRED = "missing_required"
    BAD_FORMAT = "bad_format"
    OUT_OF_RANGE = "out_of_range"
    NOT_IN_ENUM = "not_in_enum"
    LOW_CONFIDENCE = "low_confidence"
    SPELLING_VARIANT = "spelling_variant"
    # Record-level
    NON_SEQUENTIAL_SERIAL = "non_sequential_serial"
    DUPLICATE_IDENTIFIER = "duplicate_identifier"
    UNPARSED_TEXT = "unparsed_text"
    # Page-level
    GRID_FALLBACK_USED = "grid_fallback_used"
    CELL_COUNT_MISMATCH = "cell_count_mismatch"
    OCR_EMPTY = "ocr_empty"


class Issue(BaseModel):
    code: IssueCode
    severity: IssueSeverity = IssueSeverity.ERROR
    message: str
    field: str | None = None

    model_config = {"use_enum_values": True}


# ---------------------------------------------------------------------------
# Structured records
# ---------------------------------------------------------------------------


class FieldValue(BaseModel):
    """A single extracted field.

    Holds the original OCR value alongside any user edit so "reset to
    original" is always possible and exports can be audited.
    """

    key: str
    original_value: str = ""
    edited_value: str | None = None
    suggested_value: str | None = None
    """Machine-proposed correction (e.g. from cross-corpus consensus).

    Never overwrites `original_value`. The UI offers it as a one-click
    accept; `edited_value` is only set when auto-apply is enabled.
    """
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    bbox: BBox | None = None
    source_line_ids: list[str] = Field(default_factory=list)
    issues: list[Issue] = Field(default_factory=list)

    @property
    def value(self) -> str:
        """Effective value: the user's edit if present, else the OCR value."""
        return self.edited_value if self.edited_value is not None else self.original_value

    @property
    def is_edited(self) -> bool:
        return self.edited_value is not None and self.edited_value != self.original_value


class Record(BaseModel):
    """One logical entity on a page (a voter, a table row, a text block)."""

    id: str
    page_id: str
    index: int
    """Position within the page, reading order (0-based)."""
    template_id: str
    fields: dict[str, FieldValue] = Field(default_factory=dict)
    bbox: BBox | None = None
    issues: list[Issue] = Field(default_factory=list)
    reviewed: bool = False

    @property
    def min_confidence(self) -> float:
        vals = [f.confidence for f in self.fields.values() if f.original_value]
        return min(vals) if vals else 0.0

    @property
    def mean_confidence(self) -> float:
        vals = [f.confidence for f in self.fields.values() if f.original_value]
        return sum(vals) / len(vals) if vals else 0.0

    @property
    def error_count(self) -> int:
        n = sum(1 for i in self.issues if i.severity == IssueSeverity.ERROR.value)
        n += sum(
            1
            for f in self.fields.values()
            for i in f.issues
            if i.severity == IssueSeverity.ERROR.value
        )
        return n


# ---------------------------------------------------------------------------
# Template metadata
# ---------------------------------------------------------------------------


class ColumnType(str, Enum):
    TEXT = "text"
    NUMBER = "number"
    ENUM = "enum"
    IDENTIFIER = "identifier"


class ColumnDef(BaseModel):
    key: str
    label: str
    type: ColumnType = ColumnType.TEXT
    width: int = 160
    required: bool = False
    enum_values: list[str] | None = None
    description: str | None = None

    model_config = {"use_enum_values": True}


class TemplateInfo(BaseModel):
    id: str
    name: str
    description: str
    columns: list[ColumnDef]
    languages: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Pages, files, jobs
# ---------------------------------------------------------------------------


class PageStatus(str, Enum):
    PENDING = "pending"
    RENDERING = "rendering"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"


class GridSource(str, Enum):
    DETECTED = "detected"
    FALLBACK = "fallback"
    NONE = "none"


class LayoutInfo(BaseModel):
    """Result of cell detection, kept so the UI can toggle detected/fallback."""

    source: GridSource = GridSource.NONE
    confidence: float = 0.0
    cells: list[BBox] = Field(default_factory=list)
    fallback_cells: list[BBox] = Field(default_factory=list)
    rows: int = 0
    cols: int = 0
    deviation: float = 0.0

    model_config = {"use_enum_values": True}


class Page(BaseModel):
    id: str
    file_id: str
    page_number: int
    status: PageStatus = PageStatus.PENDING
    image_path: str | None = None
    width: int = 0
    height: int = 0
    template_id: str | None = None
    template_confidence: float = 0.0
    lines: list[OcrLine] = Field(default_factory=list)
    records: list[Record] = Field(default_factory=list)
    layout: LayoutInfo | None = None
    issues: list[Issue] = Field(default_factory=list)
    header_text: str = ""
    footer_text: str = ""
    ocr_ms: int = 0
    error: str | None = None

    model_config = {"use_enum_values": True}

    @property
    def full_text(self) -> str:
        return "\n".join(line.text for line in self.lines)


class FileStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled"


class SourceFile(BaseModel):
    id: str
    name: str
    size_bytes: int
    page_count: int = 0
    status: FileStatus = FileStatus.PENDING
    pages_done: int = 0
    template_id: str | None = None
    languages: list[str] = Field(default_factory=list)
    created_at: datetime
    error: str | None = None

    model_config = {"use_enum_values": True}


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Job(BaseModel):
    """Persisted so the UI can reconnect to progress after a page refresh."""

    id: str
    file_ids: list[str] = Field(default_factory=list)
    status: JobStatus = JobStatus.QUEUED
    total_pages: int = 0
    completed_pages: int = 0
    failed_pages: int = 0
    current_item: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None

    model_config = {"use_enum_values": True}

    @property
    def progress(self) -> float:
        if self.total_pages == 0:
            return 0.0
        return (self.completed_pages + self.failed_pages) / self.total_pages


class JobEvent(BaseModel):
    """SSE payload."""

    type: Literal["progress", "page_done", "file_done", "job_done", "error", "ping"]
    job_id: str
    data: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


class ExportFormat(str, Enum):
    XLSX = "xlsx"
    CSV = "csv"
    JSON = "json"
    TXT = "txt"
    MARKDOWN = "md"


class ExportMode(str, Enum):
    ALL = "all"
    CLEAN = "clean"
    """Only records with zero validation errors."""
    AUDIT = "audit"
    """Every record with original value, edited value, confidence and issues."""


class ExportRequest(BaseModel):
    format: ExportFormat
    mode: ExportMode = ExportMode.ALL
    file_ids: list[str] = Field(default_factory=list)
    page_ids: list[str] = Field(default_factory=list)
    record_ids: list[str] = Field(default_factory=list)
    include_page_numbers: bool = True
    include_confidence: bool = False
    include_issues: bool = False

    model_config = {"use_enum_values": True}

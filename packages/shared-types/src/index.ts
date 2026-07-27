/**
 * Wire contract shared between the OCR backend and the web client.
 *
 * This mirrors `apps/api/app/schemas/core.py`, which is the source of truth.
 * Field names are snake_case because that is what FastAPI serialises -- do
 * NOT camelCase them here, or every response needs a translation layer.
 *
 * When you change a model in `core.py`, change it here too. The round-trip
 * test in `apps/api/tests/test_schema_parity.py` fails the build if the two
 * drift apart.
 */

// ---------------------------------------------------------------------------
// Geometry
// ---------------------------------------------------------------------------

/** Axis-aligned box in *rendered page image* pixel coordinates. */
export interface BBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

export type Polygon = Array<[number, number]>;

// ---------------------------------------------------------------------------
// Raw OCR output (immutable)
// ---------------------------------------------------------------------------

/** One text line as returned by PaddleOCR. Never edited by the user. */
export interface OcrLine {
  id: string;
  text: string;
  /** 0..1 */
  confidence: number;
  bbox: BBox;
  polygon: Polygon;
  /** Index of the layout cell this line was assigned to, if any. */
  cell_index: number | null;
}

// ---------------------------------------------------------------------------
// Validation issues
// ---------------------------------------------------------------------------

export type IssueSeverity = 'error' | 'warning' | 'info';

export type IssueCode =
  // Field-level
  | 'missing_required'
  | 'bad_format'
  | 'out_of_range'
  | 'not_in_enum'
  | 'low_confidence'
  // Record-level
  | 'non_sequential_serial'
  | 'duplicate_identifier'
  | 'unparsed_text'
  // Page-level
  | 'grid_fallback_used'
  | 'cell_count_mismatch'
  | 'ocr_empty';

export interface Issue {
  code: IssueCode;
  severity: IssueSeverity;
  message: string;
  field: string | null;
}

// ---------------------------------------------------------------------------
// Structured records
// ---------------------------------------------------------------------------

/**
 * A single extracted field.
 *
 * `original_value` is the untouched OCR reading and `edited_value` is the
 * user's override. Keeping both is what makes "reset to original" and the
 * audit export possible -- never collapse them into one field.
 */
export interface FieldValue {
  key: string;
  original_value: string;
  edited_value: string | null;
  suggested_value?: string | null;
  /** 0..1 */
  confidence: number;
  bbox: BBox | null;
  source_line_ids: string[];
  issues: Issue[];
}

export interface Record_ {
  id: string;
  page_id: string;
  /** Position within the page, reading order (0-based). */
  index: number;
  template_id: string;
  fields: Record<string, FieldValue>;
  bbox: BBox | null;
  issues: Issue[];
  reviewed: boolean;
  mean_confidence?: number;
}

// ---------------------------------------------------------------------------
// Template metadata
// ---------------------------------------------------------------------------

export type ColumnType = 'text' | 'number' | 'enum' | 'identifier';

export interface ColumnDef {
  key: string;
  label: string;
  type: ColumnType;
  width: number;
  required: boolean;
  enum_values: string[] | null;
  description: string | null;
}

export interface TemplateInfo {
  id: string;
  name: string;
  description: string;
  columns: ColumnDef[];
  languages: string[];
}

// ---------------------------------------------------------------------------
// Pages, files, jobs
// ---------------------------------------------------------------------------

export type PageStatus =
  | 'pending'
  | 'rendering'
  | 'processing'
  | 'completed'
  | 'error';

export type GridSource = 'detected' | 'fallback' | 'none';

/** Result of cell detection. Both grids are kept so the UI can offer a toggle. */
export interface LayoutInfo {
  source: GridSource;
  confidence: number;
  cells: BBox[];
  fallback_cells: BBox[];
  rows: number;
  cols: number;
  deviation: number;
}

export interface Page {
  id: string;
  file_id: string;
  page_number: number;
  status: PageStatus;
  /** Filename within the pages directory; served from `/api/pages/{id}/image`. */
  image_path: string | null;
  width: number;
  height: number;
  template_id: string | null;
  template_confidence: number;
  lines: OcrLine[];
  records: Record_[];
  layout: LayoutInfo | null;
  issues: Issue[];
  header_text: string;
  footer_text: string;
  ocr_ms: number;
  error: string | null;
}

export type FileStatus =
  | 'pending'
  | 'processing'
  | 'completed'
  | 'error'
  | 'cancelled';

export interface SourceFile {
  id: string;
  name: string;
  size_bytes: number;
  page_count: number;
  status: FileStatus;
  pages_done: number;
  template_id: string | null;
  languages: string[];
  created_at: string;
  error: string | null;
}

export type JobStatus =
  | 'queued'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled';

/** Persisted so the UI can reconnect to progress after a page refresh. */
export interface Job {
  id: string;
  file_ids: string[];
  status: JobStatus;
  total_pages: number;
  completed_pages: number;
  failed_pages: number;
  current_item: string | null;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
}

export type JobEventType =
  | 'progress'
  | 'page_done'
  | 'file_done'
  | 'job_done'
  | 'error'
  | 'ping';

/** SSE payload from `/api/jobs/{id}/events`. */
export interface JobEvent {
  type: JobEventType;
  job_id: string;
  data: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------

export type ExportFormat = 'xlsx' | 'csv' | 'json' | 'txt' | 'md';

/**
 * `clean` exports only records with zero validation errors.
 * `audit` exports every record with original value, edited value,
 * confidence and issues -- for quality checking.
 */
export type ExportMode = 'all' | 'clean' | 'audit';

export interface ExportRequest {
  format: ExportFormat;
  mode: ExportMode;
  file_ids: string[];
  page_ids: string[];
  record_ids: string[];
  include_page_numbers: boolean;
  include_confidence: boolean;
  include_issues: boolean;
}

// ---------------------------------------------------------------------------
// Client-side helpers
// ---------------------------------------------------------------------------

/** Effective value: the user's edit if present, else the OCR reading. */
export function fieldValue(field: FieldValue | undefined): string {
  if (!field) return '';
  return field.edited_value !== null && field.edited_value !== undefined
    ? field.edited_value
    : field.original_value;
}

export function isEdited(field: FieldValue | undefined): boolean {
  if (!field) return false;
  return (
    field.edited_value !== null &&
    field.edited_value !== undefined &&
    field.edited_value !== field.original_value
  );
}

export function allIssues(record: Record_): Issue[] {
  return [
    ...record.issues,
    ...Object.values(record.fields).flatMap((f) => f.issues),
  ];
}

export function errorCount(record: Record_): number {
  return allIssues(record).filter((i) => i.severity === 'error').length;
}

export function warningCount(record: Record_): number {
  return allIssues(record).filter((i) => i.severity === 'warning').length;
}

/** True when a record needs human attention. Drives the review queue. */
export function needsReview(record: Record_): boolean {
  return !record.reviewed && errorCount(record) > 0;
}

export function meanConfidence(record: Record_): number {
  const values = Object.values(record.fields)
    .filter((f) => f.original_value)
    .map((f) => f.confidence);
  if (values.length === 0) return 0;
  return values.reduce((a, b) => a + b, 0) / values.length;
}

/** Confidence band used for colour coding. */
export type ConfidenceBand = 'high' | 'medium' | 'low';

export function confidenceBand(confidence: number): ConfidenceBand {
  if (confidence >= 0.85) return 'high';
  if (confidence >= 0.6) return 'medium';
  return 'low';
}

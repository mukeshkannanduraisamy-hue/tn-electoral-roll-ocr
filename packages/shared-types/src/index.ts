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

export type PhotoType =
  | 'voter_crop'
  | 'station_front'
  | 'station_building'
  | 'nazri_naksha'
  | 'google_map'
  | 'cad_map'
  | 'key_map';

/** An image cropped out of a roll page. */
export interface Photo {
  id: string;
  photo_type: PhotoType;
  file_id: string | null;
  page_id: string | null;
  record_id: string | null;
  voter_id: string | null;
  polling_station_id: string | null;
  width: number;
  height: number;
  /** Fetch the image itself from here. */
  url: string;
  created_at: string | null;
}

export interface PhotoList {
  items: Photo[];
  total: number;
}

/** One field's OCR provenance, with its box on the 0–1000 grid. */
export interface OcrBlock {
  id: string;
  field_name: string;
  /** [x0, y0, x1, y1] on a 0–1000 grid — scale by the displayed page size. */
  bbox: [number, number, number, number];
  raw_text: string;
  corrected_text: string;
  edited: boolean;
  confidence: number;
}

/** Response of `GET /api/voters/{id}/ocr-blocks`. */
export interface VoterOcrBlocks {
  voter_id: string;
  record_id: string | null;
  page_id: string | null;
  page_number: number | null;
  page_width: number;
  page_height: number;
  page_type: PageType | "";
  /** The grid `bbox` values are expressed on. Always 1000. */
  bbox_scale: number;
  mean_confidence: number;
  min_confidence: number;
  blocks: OcrBlock[];
}

export type AuditAction = 'created' | 'updated' | 'deleted' | 'promoted';

export interface AuditEntry {
  id: string;
  action: AuditAction;
  /** Empty for create/delete, which are logged once rather than per field. */
  field_name: string;
  old_value: string | null;
  new_value: string | null;
  user: string;
  timestamp: string | null;
}

/** Response of `GET /api/voters/{id}/history`, newest first. */
export interface VoterHistory {
  voter_id: string;
  total: number;
  entries: AuditEntry[];
}

/**
 * Extracted record count against the total the roll itself prints.
 *
 * `difference` is signed: positive means more records were extracted than
 * the roll says exist (a page counted twice, a misdetected grid); negative
 * means records are missing. `null` when neither sheet was readable.
 */
export interface PartReconciliation {
  extracted_records: number;
  printed_total: number | null;
  difference: number | null;
  reconciled: boolean;
  /** Which sheet `printed_total` came from: `summary` or `cover`. */
  source: string;
  base_total: number;
  additions_total: number;
  deletions_total: number;
  corrections: number;
}

/** One part, read off its cover sheet. Served by `/api/polling-stations`. */
export interface PollingStation {
  id: string;
  file_id: string;
  part_number: string;
  name: string;
  name_tam: string;
  building_name: string;
  section_details: string;

  ac_number: string;
  ac_name: string;
  pc_number: string;
  pc_name: string;

  station_number: string;
  /** ஆண் / பெண் / பொது — men's, women's or general. */
  station_type: string;
  address: string;

  district: string;
  taluk: string;
  pincode: string;

  serial_start: number | null;
  serial_end: number | null;
  total_electors: number;
  male_electors: number;
  female_electors: number;
  third_gender_electors: number;
  voter_count: number;

  source_page_id: string;
  /** Full cover-sheet detail, including fields not broken out above. */
  details: Record<string, unknown>;
  reconciliation: PartReconciliation | null;
  photo_count: number;
  photos: Array<{
    id: string;
    photo_type: string;
    file_path: string;
    width?: number;
    height?: number;
  }>;
  created_at: string | null;
}

/** Mirrors `services.page_classifier.PageType`. */
export type PageType =
  | 'cover_page'
  | 'map_photo_page'
  | 'voter_list_page'
  | 'supplement_page'
  | 'summary_page'
  | 'legend_page'
  | 'blank_or_signature'
  | 'other';

/** The page types that carry voter records. */
export const VOTER_BEARING_PAGE_TYPES: readonly PageType[] = [
  'voter_list_page',
  'supplement_page',
];

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
  /**
   * What kind of sheet this is. Only `voter_list_page` and `supplement_page`
   * carry records; the rest are kept for their text and images.
   */
  page_type: PageType;
  classification_confidence: number;
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

// ---------------------------------------------------------------------------
// Authentication
// ---------------------------------------------------------------------------

export interface AuthUser {
  id: string;
  username: string;
  display_name: string;
  last_login_at: string | null;
}

export interface AuthStatus {
  auth_enabled: boolean;
  authenticated: boolean;
  user: AuthUser | null;
}

// ---------------------------------------------------------------------------
// Curated voter records
//
// Distinct from `Record_`, which is raw OCR output. A Voter has been reviewed
// and promoted, which is why `epic` is guaranteed unique here and not there.
// ---------------------------------------------------------------------------

export type Gender = 'Male' | 'Female' | 'Other';
export type RelationType = 'Husband' | 'Father' | 'Mother' | 'Other';

export interface Voter {
  id: string;
  epic: string;
  name: string;
  serial: number | null;
  relation_type: RelationType | '';
  relation_name: string;
  house_number: string;
  age: number | null;
  gender: Gender | '';
  part_number: string;
  constituency: string;
  notes: string;
  verified: boolean;
  polling_station_id: string | null;
  /**
   * Added by a supplement rather than carried from the base roll. Not
   * cosmetic: a supplement elector joined after the base list was
   * published, and a report that conflates the two misstates the revision.
   */
  is_supplement: boolean;
  source_record_id: string | null;
  source_page_id: string | null;
  source_file_id: string | null;
  source_file_name: string;
  page_number: number | null;
  page_id: string | null;
  created_at: string;
  updated_at: string;
  created_by: string;
  updated_by: string;
}

// ---------------------------------------------------------------------------
// Family tree
//
// Resolved server-side by app/services/family_tree_solver.py. The client does
// not re-derive relationships: the roll's Tamil relation labels, the fuzzy name
// matching and the genealogical constraints all live in one place.
// ---------------------------------------------------------------------------

export type ConfidenceLevel = 'Confirmed' | 'Strong' | 'Possible' | 'Unverified';

/** Position in the resolved graph, derived from edges rather than edge order. */
export type ResolvedRole =
  | 'Father'
  | 'Mother'
  | 'Parent'
  | 'Son'
  | 'Daughter'
  | 'Child'
  | 'Husband'
  | 'Wife'
  | 'Spouse'
  | 'Resident';

/** A voter plus their place in the household graph. */
export interface FamilyMember extends Voter {
  resolved_role: ResolvedRole;
  /** 1 is the senior generation; each step down adds one. */
  generation_level: number;
  is_head: boolean;
  spouse_id: string | null;
  parent_ids: string[];
  child_ids: string[];
}

/** Per-term breakdown of why a link scored what it did. */
export interface RelationshipEvidence {
  /** 30 for an exact house match, 15 for serial-window proximity. */
  locality_score: number;
  /** Jaro-Winkler similarity, 0–1. */
  name_score: number;
  name_points: number;
  relation_points: number;
  /** False when the ages contradict *or* when they were never recorded. */
  age_valid: boolean;
  /** Distinguishes "check failed" from "check could not run". */
  age_known: boolean;
  gender_valid: boolean;
  gender_known: boolean;
}

/** An accepted edge. `source` declared `relationship_type` naming `target`. */
export interface FamilyRelationship {
  source_id: string;
  source_name: string;
  target_id: string;
  target_name: string;
  relationship_type: RelationType;
  confidence: number;
  confidence_level: ConfidenceLevel;
  evidence: RelationshipEvidence;
}

/**
 * A link the roll asserts but the evidence contradicts — a father younger than
 * his child, a woman recorded as another woman's husband. Surfaced rather than
 * silently dropped, because it marks a record worth re-reading.
 */
export interface RejectedLink {
  source_id: string;
  source_name: string;
  target_id: string;
  target_name: string;
  relationship_type: RelationType | '';
  reason: string;
}

/** Why a family resolved no relationships at all. */
export type UnresolvedReason =
  /** Nothing to resolve: no relative named on the roll. */
  | 'no_relation_recorded'
  /** A relative was named but is not registered at this address. */
  | 'relative_not_in_household'
  /** Links were asserted but every one contradicted the evidence. */
  | 'contradicted';

export interface FamilyTree {
  family_id: string;
  family_head: string;
  house_number: string;
  locality: 'house' | 'serial_window';
  members: FamilyMember[];
  relationships: FamilyRelationship[];
  rejected_links: RejectedLink[];
  /** Senior-generation members, already deduplicated across married pairs. */
  root_ids: string[];
  generation_count: number;
  ascii_tree: string;
  /** Mean of the resolved edges; 0 when nothing resolved. */
  confidence: number;
  confidence_level: ConfidenceLevel;
  unresolved_reason: UnresolvedReason | null;
}

export interface Household {
  house_number: string;
  /**
   * Canonical building the address resolves to. The roll spells one address
   * several ways ("2-332", "2/332", "2/332-1"), so members are grouped on this
   * rather than on the literal value.
   */
  building_key: string;
  /** Every spelling this address appears under in the roll. */
  house_variants: string[];
  part_number: string;
  constituency: string;
  size: number;
  /** How the household was identified when no house number was recorded. */
  grouping: 'house' | 'serial_window';
  /** True when the address hit the row cap, so members may be missing. */
  truncated: boolean;
}

export interface FamilyTreeResponse {
  target_voter_id: string;
  household: Household;
  /** The family containing the target voter; null only for an empty household. */
  primary_family_id: string | null;
  /** Every family at the address — unresolved members form their own. */
  families: FamilyTree[];
}

// ---------------------------------------------------------------------------
// Infographics
//
// Built by app/services/infographic.py. Every figure here was produced by SQL
// over the voter table — the language model only chooses which measure to chart
// and writes `insights`, and any figure it quotes is checked against these
// values before being returned. So the numbers are safe to render as-is.
// ---------------------------------------------------------------------------

export type InfographicChartType = 'stat' | 'bar' | 'column' | 'donut';

/** How to format a value. `count` is an integer, `percent` is 0-100. */
export type MetricUnit = 'count' | 'percent' | 'years';

export interface InfographicPoint {
  label: string;
  value: number | null;
  /** Percent of the total. Null when the parts do not sum to a whole. */
  share: number | null;
}

export interface InfographicMetric {
  key: string;
  label: string;
  unit: MetricUnit;
  description: string;
}

export interface InfographicHighlight {
  label: string;
  value: number | null;
  unit: MetricUnit;
  share?: number | null;
}

export interface InfographicFilter {
  key: string;
  label: string;
  value: string;
}

export interface Infographic {
  title: string;
  chart_type: InfographicChartType;
  metric: InfographicMetric;
  /** Null when the figure has no breakdown, which renders as a stat tile. */
  dimension: { key: string; label: string } | null;
  series: InfographicPoint[];
  total: number | null;
  /** Electors the figures describe, after filters and before grouping. */
  population: number;
  highlights: InfographicHighlight[];
  filters_applied: InfographicFilter[];
  /** Groups folded into "Other", or omitted when the measure cannot be summed. */
  truncated_groups: number;
  /** Model-written commentary, already stripped of unverifiable figures. */
  insights: string[];
  generated_at: string;
  provenance: string;
}

export interface AiCopilotResponse {
  reply: string;
  /** Present only when the question was statistical. */
  infographic?: Infographic | null;
  /** False when no API key is set, so the reply came from the offline guide. */
  ai_configured?: boolean;
}

// ---------------------------------------------------------------------------
// The agentic assistant
//
// Blocks are built by the server from tool results, never by the model. That is
// deliberate: asking a language model to emit a table is asking it to retype
// data it was just given, and a retyped table is a table with a typo in it.
// ---------------------------------------------------------------------------

export interface ChatTableBlock {
  kind: "table";
  columns: string[];
  rows: Record<string, unknown>[];
  total?: number | null;
  truncated?: boolean;
}

export interface ChatVoterCardBlock {
  kind: "voter_card";
  voter: Record<string, unknown>;
  provenance: Record<string, unknown>;
  ocr_fields: {
    field_name: string;
    raw_text: string;
    corrected_text: string;
    confidence: number;
    bbox: number[];
  }[];
}

export interface ChatChartBlock {
  kind: "chart";
  infographic: Infographic;
}

export interface ChatSqlBlock {
  kind: "sql";
  sql: string;
  rationale: string;
  returned: number;
}

export type ChatBlock =
  | ChatTableBlock
  | ChatVoterCardBlock
  | ChatChartBlock
  | ChatSqlBlock;

/** An elector a tool actually returned. Anything else was stripped server-side. */
export interface ChatCitation {
  id: string;
  epic: string | null;
  name: string | null;
  part_number: string | null;
}

export interface ChatToolStep {
  tool: string;
  args?: Record<string, unknown>;
  ok: boolean;
  returned?: number | null;
  error?: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  blocks: ChatBlock[];
  citations: ChatCitation[];
  tool_trace: ChatToolStep[];
  created_at?: string | null;
  /** True when the turn hit MAX_ROUNDS/MAX_TOOL_CALLS/the deadline before finishing. */
  budget_exhausted?: boolean;
  /** Set when `stream_chat` failed outright (rate limit, timeout, ...) and the
   *  turn's content is a bracketed provider notice rather than assistant prose.
   *  Distinguishes "the provider stopped early" from "the figures didn't support
   *  an answer" -- the two collapse to the same empty `verified` result server-side. */
  provider_notice?: string | null;
  /** Set locally while the reply is still streaming. */
  pending?: boolean;
  /** Set when the turn ended in an error rather than an answer. */
  failed?: boolean;
}

export interface ChatThreadSummary {
  id: string;
  title: string;
  updated_at: string | null;
}

export interface ChatThread extends ChatThreadSummary {
  messages: ChatMessage[];
}

export type AgentStreamEvent =
  | { type: "status"; data: { message?: string; thread_id?: string; intent?: string } }
  | { type: "tool_call"; data: { id: string; name: string; label: string; args: Record<string, unknown> } }
  | { type: "tool_result"; data: { id: string; name: string; ok: boolean; error?: string; summary?: ChatToolStep } }
  | { type: "token"; data: { text: string } }
  | { type: "blocks"; data: { blocks: ChatBlock[] } }
  | { type: "citations"; data: { citations: ChatCitation[] } }
  | { type: "done"; data: { content: string; blocks: ChatBlock[]; citations: ChatCitation[]; tool_trace: ChatToolStep[]; budget_exhausted?: boolean; provider_notice?: string | null } }
  | { type: "error"; data: { message: string } };


/**
 * AI configuration as the server reports it. The API key is write-only over the
 * HTTP surface: it can be set, tested and cleared, but is never returned — only
 * `key_hint` comes back, so an operator can tell which key is stored.
 */
export interface AiSettings {
  configured: boolean;
  /** Masked, e.g. `nvapi-…mOzN`. Empty when nothing is configured. */
  key_hint: string;
  /** Where the active key came from. */
  source: 'settings' | 'environment' | 'none';
  base_url: string;
  model: string;
  updated_at: string | null;
  updated_by: string | null;
}

/** Omit a field to leave it unchanged; send an empty string to clear it. */
export interface AiSettingsUpdate {
  api_key?: string;
  base_url?: string;
  model?: string;
}

export interface AiSettingsTest {
  ok: boolean;
  detail: string;
  model?: string;
}

/** Fields a user may set. Server-managed columns are omitted. */
export type VoterInput = Pick<
  Voter,
  | 'epic'
  | 'name'
  | 'serial'
  | 'relation_type'
  | 'relation_name'
  | 'house_number'
  | 'age'
  | 'gender'
  | 'part_number'
  | 'constituency'
  | 'notes'
  | 'verified'
>;

export interface VoterPage {
  items: Voter[];
  total: number;
  offset: number;
  limit: number;
}

export interface VoterQuery {
  search?: string;
  gender?: string;
  relation_type?: string;
  part_number?: string;
  constituency?: string;
  house_number?: string;
  has_photo?: boolean;
  polling_station_id?: string;
  is_supplement?: boolean;
  min_serial?: number;
  max_serial?: number;
  min_page?: number;
  max_page?: number;
  source_file_name?: string;
  source_file_id?: string;
  verified?: boolean;
  min_age?: number;
  max_age?: number;
  sort?: string;
  order?: 'asc' | 'desc';
  offset?: number;
  limit?: number;
}

export interface VoterStats {
  total: number;
  verified: number;
  unverified: number;
  by_gender: Record<string, number>;
  by_relation_type: Record<string, number>;
  age_buckets: Record<string, number>;
  by_part: Array<{ part: string; count: number }>;
  average_age: number | null;
  missing_age: number;
}

/** A record that could not be promoted, and why. */
export interface PromotionConflict {
  record_id: string;
  epic: string;
  reason: string;
  existing_voter_id: string | null;
  existing_name: string;
  incoming_name: string;
}

export interface PromotionResult {
  created: number;
  updated: number;
  skipped: number;
  conflicts: PromotionConflict[];
  voter_ids: string[];
}

export type VoterExportFormat = 'xlsx' | 'csv' | 'pdf';

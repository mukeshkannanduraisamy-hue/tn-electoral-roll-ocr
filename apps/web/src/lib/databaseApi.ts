/**
 * API client for the read-only database introspection viewer.
 *
 * Every call goes through the shared `request` helper from voterApi
 * which handles auth cookies and 401 redirects.
 */

// Re-use the same authenticated request helper
const API_BASE = (
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_API_BASE ||
  ""
).replace(/\/$/, "");

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const url = path.startsWith("http") ? path : `${API_BASE}${path}`;
  const res = await fetch(url, {
    credentials: API_BASE ? "include" : "same-origin",
    headers:
      init.body && !(init.body instanceof FormData)
        ? { "Content-Type": "application/json", ...(init.headers ?? {}) }
        : init.headers,
    ...init,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const detail =
      typeof body?.detail === "string" ? body.detail : `Request failed (${res.status})`;
    throw new Error(detail);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface DbTableInfo {
  name: string;
  row_count: number;
  column_count: number;
  type: "table" | "view";
}

export interface DbColumn {
  name: string;
  type: string;
  pk: boolean;
  nullable: boolean;
  dflt_value: string | null;
}

export interface DbIndex {
  name: string;
  unique: boolean;
  columns: string[];
}

export interface DbRowsResponse {
  columns: string[];
  rows: Record<string, unknown>[];
  total: number;
  page: number;
  page_size: number;
}

export interface DbQueryResult {
  columns: string[];
  rows: Record<string, unknown>[];
  row_count: number;
  duration_ms: number;
}

export interface DbStats {
  sqlite_version: string;
  file_size_bytes: number;
  file_size_display: string;
  table_count: number;
  view_count: number;
  index_count: number;
  page_count: number;
  page_size: number;
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

export function fetchDbStats(): Promise<DbStats> {
  return request<DbStats>("/api/database/stats");
}

export function fetchTables(): Promise<DbTableInfo[]> {
  return request<DbTableInfo[]>("/api/database/tables");
}

export function fetchColumns(table: string): Promise<DbColumn[]> {
  return request<DbColumn[]>(`/api/database/tables/${encodeURIComponent(table)}/columns`);
}

export function fetchIndexes(table: string): Promise<DbIndex[]> {
  return request<DbIndex[]>(`/api/database/tables/${encodeURIComponent(table)}/indexes`);
}

export function fetchRows(
  table: string,
  params: {
    page?: number;
    page_size?: number;
    sort?: string;
    order?: "asc" | "desc";
    search?: string;
  } = {},
): Promise<DbRowsResponse> {
  const qs = new URLSearchParams();
  if (params.page) qs.set("page", String(params.page));
  if (params.page_size) qs.set("page_size", String(params.page_size));
  if (params.sort) qs.set("sort", params.sort);
  if (params.order) qs.set("order", params.order);
  if (params.search) qs.set("search", params.search);
  const suffix = qs.toString() ? `?${qs}` : "";
  return request<DbRowsResponse>(
    `/api/database/tables/${encodeURIComponent(table)}/rows${suffix}`,
  );
}

export function executeQuery(sql: string): Promise<DbQueryResult> {
  return request<DbQueryResult>("/api/database/query", {
    method: "POST",
    body: JSON.stringify({ sql }),
  });
}

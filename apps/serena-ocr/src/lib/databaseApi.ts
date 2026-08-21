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

const API_BASE = (
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_API_BASE ||
  ""
).replace(/\/$/, "");

async function dbFetch(url: string, init?: RequestInit): Promise<Response> {
  const target = url.startsWith("http") ? url : `${API_BASE}${url}`;
  const res = await fetch(target, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  if (res.status === 401) {
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("serena:unauthorized"));
    }
  }

  return res;
}

export async function fetchDbStats(): Promise<DbStats> {
  const res = await dbFetch("/api/database/stats");
  if (!res.ok) throw new Error("Failed to fetch database statistics");
  return res.json();
}

export async function fetchTables(): Promise<DbTableInfo[]> {
  const res = await dbFetch("/api/database/tables");
  if (!res.ok) throw new Error("Failed to fetch tables list");
  return res.json();
}

export async function fetchColumns(tableName: string): Promise<DbColumn[]> {
  const res = await dbFetch(`/api/database/tables/${encodeURIComponent(tableName)}/columns`);
  if (!res.ok) throw new Error(`Failed to fetch columns for table ${tableName}`);
  return res.json();
}

export async function fetchIndexes(tableName: string): Promise<DbIndex[]> {
  const res = await dbFetch(`/api/database/tables/${encodeURIComponent(tableName)}/indexes`);
  if (!res.ok) throw new Error(`Failed to fetch indexes for table ${tableName}`);
  return res.json();
}

export async function fetchRows(
  tableName: string,
  page = 1,
  pageSize = 50,
  search?: string,
  sort?: string,
  order: "asc" | "desc" = "asc"
): Promise<DbRowsResponse> {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
    order,
  });
  if (search) params.set("search", search);
  if (sort) params.set("sort", sort);

  const res = await dbFetch(
    `/api/database/tables/${encodeURIComponent(tableName)}/rows?${params.toString()}`
  );
  if (!res.ok) throw new Error(`Failed to fetch rows for table ${tableName}`);
  return res.json();
}

export async function executeQuery(sql: string): Promise<DbQueryResult> {
  const res = await dbFetch("/api/database/query", {
    method: "POST",
    body: JSON.stringify({ sql }),
  });
  if (!res.ok) {
    const errorJson = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(errorJson.detail || "Query execution failed");
  }
  return res.json();
}

export async function promoteAllToDb(): Promise<{ created: number; updated: number; skipped: number }> {
  const res = await dbFetch("/api/voters/promote-all", {
    method: "POST",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Failed to promote all" }));
    throw new Error(err.detail || "Bulk promotion failed");
  }
  return res.json();
}

export async function truncateTable(tableName: string): Promise<void> {
  const res = await dbFetch(`/api/database/tables/${encodeURIComponent(tableName)}/truncate`, {
    method: "POST",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Failed to truncate table" }));
    throw new Error(err.detail || `Failed to truncate table ${tableName}`);
  }
}

export async function truncateAllTables(): Promise<void> {
  const res = await dbFetch("/api/database/truncate-all", {
    method: "POST",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Failed to truncate all tables" }));
    throw new Error(err.detail || "Failed to truncate database");
  }
}

export function downloadCsv(filename: string, columns: string[], rows: Record<string, unknown>[]): void {
  const escapeCell = (val: unknown) => {
    if (val === null || val === undefined) return "";
    const str = typeof val === "object" ? JSON.stringify(val) : String(val);
    if (str.includes(",") || str.includes('"') || str.includes("\n")) {
      return `"${str.replace(/"/g, '""')}"`;
    }
    return str;
  };

  const headerLine = columns.map(escapeCell).join(",");
  const bodyLines = rows.map((r) => columns.map((col) => escapeCell(r[col])).join(","));
  const csvContent = [headerLine, ...bodyLines].join("\r\n");

  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.setAttribute("href", url);
  link.setAttribute("download", filename);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

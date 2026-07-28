/**
 * API client for authentication and the curated voter table.
 *
 * Every call goes through `request`, which centralises two things that are
 * easy to get wrong per-call: sending the session cookie, and turning a 401
 * into a single app-wide "you are signed out" signal rather than a random
 * failure in whichever component happened to fetch first.
 */

import {
  AuthStatus,
  AuthUser,
  PhotoList,
  PollingStation,
  PromotionResult,
  Voter,
  VoterExportFormat,
  VoterHistory,
  VoterInput,
  VoterOcrBlocks,
  VoterPage,
  VoterQuery,
  VoterStats,
} from "@ocr/shared-types";

/** Notified when the server says the session is gone. */
type UnauthorizedHandler = () => void;
let onUnauthorized: UnauthorizedHandler | null = null;

export function setUnauthorizedHandler(handler: UnauthorizedHandler | null) {
  onUnauthorized = handler;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly detail?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Pull a readable message out of FastAPI's several error shapes. */
function describe(status: number, body: unknown): string {
  if (typeof body === "string" && body) return body;
  const detail = (body as { detail?: unknown })?.detail;
  if (typeof detail === "string") return detail;

  // 422 from Pydantic: [{loc: [...], msg: "..."}]
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        const field = Array.isArray(d?.loc) ? d.loc.filter((p: unknown) => p !== "body").join(".") : "";
        const msg = String(d?.msg ?? "invalid").replace(/^Value error,\s*/, "");
        return field ? `${field}: ${msg}` : msg;
      })
      .join("; ");
  }
  return `Request failed (${status})`;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    // The session lives in an HttpOnly cookie, so it must be sent explicitly.
    credentials: "same-origin",
    headers:
      init.body && !(init.body instanceof FormData)
        ? { "Content-Type": "application/json", ...(init.headers ?? {}) }
        : init.headers,
    ...init,
  });

  if (res.status === 401) {
    onUnauthorized?.();
    throw new ApiError("Your session has expired. Please sign in again.", 401);
  }

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(describe(res.status, body), res.status, body);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export function authStatus(): Promise<AuthStatus> {
  return request<AuthStatus>("/api/auth/status");
}

export function login(username: string, password: string): Promise<AuthUser> {
  return request<AuthUser>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function logout(): Promise<void> {
  return request<void>("/api/auth/logout", { method: "POST" });
}

export function changePassword(
  current_password: string,
  new_password: string,
): Promise<void> {
  return request<void>("/api/auth/password", {
    method: "POST",
    body: JSON.stringify({ current_password, new_password }),
  });
}

// ---------------------------------------------------------------------------
// Voters
// ---------------------------------------------------------------------------

function toQuery(query: Record<string, unknown>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === "") continue;
    params.set(key, String(value));
  }
  const s = params.toString();
  return s ? `?${s}` : "";
}

export function listVoters(query: VoterQuery = {}): Promise<VoterPage> {
  return request<VoterPage>(`/api/voters${toQuery(query as Record<string, unknown>)}`);
}

export function getVoter(id: string): Promise<Voter> {
  return request<Voter>(`/api/voters/${id}`);
}

export function createVoter(input: VoterInput): Promise<Voter> {
  return request<Voter>("/api/voters", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function updateVoter(id: string, patch: Partial<VoterInput>): Promise<Voter> {
  return request<Voter>(`/api/voters/${id}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export function deleteVoter(id: string): Promise<void> {
  return request<void>(`/api/voters/${id}`, { method: "DELETE" });
}

export function bulkDeleteVoters(
  voter_ids: string[],
): Promise<{ deleted: number; requested: number }> {
  return request("/api/voters/bulk-delete", {
    method: "POST",
    body: JSON.stringify({ voter_ids }),
  });
}

export function voterStats(): Promise<VoterStats> {
  return request<VoterStats>("/api/voters/stats");
}

export function voterOcrBlocks(id: string): Promise<VoterOcrBlocks> {
  return request<VoterOcrBlocks>(`/api/voters/${id}/ocr-blocks`);
}

export function voterHistory(id: string): Promise<VoterHistory> {
  return request<VoterHistory>(`/api/voters/${id}/history`);
}

export function listPhotos(query: {
  voter_id?: string;
  polling_station_id?: string;
  file_id?: string;
  photo_type?: string;
}): Promise<PhotoList> {
  return request<PhotoList>(`/api/photos${toQuery(query as Record<string, unknown>)}`);
}

export function listPollingStations(query: {
  file_id?: string;
  part_number?: string;
  district?: string;
  search?: string;
  reconciled?: boolean;
  limit?: number;
}): Promise<{ items: PollingStation[]; total: number }> {
  return request(`/api/polling-stations${toQuery(query as Record<string, unknown>)}`);
}

export function promoteRecords(payload: {
  record_ids?: string[];
  file_id?: string;
  page_id?: string;
  only_clean?: boolean;
  on_conflict?: "skip" | "update";
}): Promise<PromotionResult> {
  return request<PromotionResult>("/api/voters/promote", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/**
 * Download an export. Filters mirror the list view, so the file matches what
 * is on screen.
 */
export async function downloadVoterExport(
  format: VoterExportFormat,
  query: VoterQuery & { include_meta?: boolean } = {},
): Promise<void> {
  const res = await fetch(
    `/api/voters/export${toQuery({ format, ...query } as Record<string, unknown>)}`,
    { credentials: "same-origin" },
  );

  if (res.status === 401) {
    onUnauthorized?.();
    throw new ApiError("Your session has expired. Please sign in again.", 401);
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(describe(res.status, body), res.status, body);
  }

  const blob = await res.blob();
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const match = disposition.match(/filename="?([^"]+)"?/);
  const filename = match?.[1] ?? `voters.${format}`;

  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

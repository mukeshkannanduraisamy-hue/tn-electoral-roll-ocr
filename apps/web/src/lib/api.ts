import {
  ExportRequest,
  FileStatus,
  Job,
  Page,
  Record_,
  SourceFile,
  TemplateInfo,
} from "@ocr/shared-types";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || process.env.NEXT_PUBLIC_API_BASE || "").replace(/\/$/, "");

export interface RecordPageResponse {
  items: Record_[];
  total: number;
  offset: number;
  limit: number;
}

export interface RecordStats {
  total: number;
  with_errors: number;
  with_warnings: number;
  edited: number;
  reviewed: number;
  clean: number;
}

export interface RecordQuery {
  file_id?: string;
  page_id?: string;
  search?: string;
  only_issues?: boolean;
  only_edited?: boolean;
  unreviewed?: boolean;
  min_confidence?: number;
  max_confidence?: number;
  offset?: number;
  limit?: number;
}

export interface FieldEdit {
  key: string;
  value: string | null;
}

export interface RecordUpdatePayload {
  edits?: FieldEdit[];
  reviewed?: boolean;
}

export interface BulkUpdatePayload {
  record_ids: string[];
  reviewed?: boolean;
  accept_suggestions?: boolean;
  reset_all?: boolean;
}

async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const url = path.startsWith("http") ? path : `${API_BASE}${path}`;
  return fetch(url, {
    credentials: API_BASE ? "include" : "same-origin",
    ...init,
    headers: {
      ...(init.body && !(init.body instanceof FormData)
        ? { "Content-Type": "application/json" }
        : {}),
      ...(init.headers || {}),
    },
  });
}


export async function fetchFiles(): Promise<SourceFile[]> {
  const res = await apiFetch(`${API_BASE}/api/files`);
  if (!res.ok) throw new Error("Failed to fetch files");
  return res.json();
}

export async function uploadFiles(files: File[]): Promise<SourceFile[]> {
  const formData = new FormData();
  files.forEach((f) => formData.append("files", f));

  const res = await apiFetch(`${API_BASE}/api/files`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Upload failed" }));
    throw new Error(err.detail || "Upload failed");
  }
  return res.json();
}

export async function importFolder(path: string, recursive = true): Promise<SourceFile[]> {
  const res = await apiFetch(`${API_BASE}/api/files/import-folder`, {
    method: "POST",
    body: JSON.stringify({ path, recursive }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Folder import failed" }));
    throw new Error(err.detail || "Folder import failed");
  }
  return res.json();
}

export async function deleteFile(fileId: string): Promise<void> {
  const res = await apiFetch(`${API_BASE}/api/files/${fileId}`, {
    method: "DELETE",
  });
  if (!res.ok && res.status !== 404) {
    const err = await res.json().catch(() => ({ detail: "Failed to delete file" }));
    throw new Error(err.detail || "Failed to delete file");
  }
}

export async function fetchFilePages(fileId: string): Promise<any[]> {
  const res = await apiFetch(`${API_BASE}/api/files/${fileId}/pages`);
  if (!res.ok) throw new Error("Failed to fetch page index");
  return res.json();
}

export async function fetchPage(pageId: string): Promise<Page> {
  const res = await apiFetch(`${API_BASE}/api/pages/${pageId}`);
  if (!res.ok) throw new Error("Failed to fetch page details");
  return res.json();
}

export async function reocrPage(
  pageId: string,
  templateId = "auto",
  upscale?: number
): Promise<Page> {
  const params = new URLSearchParams({ template_id: templateId });
  if (upscale) params.set("upscale", upscale.toString());

  const res = await apiFetch(`${API_BASE}/api/pages/${pageId}/reocr?${params}`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Re-OCR failed");
  return res.json();
}

export async function fetchRecords(query: RecordQuery): Promise<RecordPageResponse> {
  const params = new URLSearchParams();
  if (query.file_id) params.set("file_id", query.file_id);
  if (query.page_id) params.set("page_id", query.page_id);
  if (query.search) params.set("search", query.search);
  if (query.only_issues) params.set("only_issues", "true");
  if (query.only_edited) params.set("only_edited", "true");
  if (query.unreviewed) params.set("unreviewed", "true");
  if (query.min_confidence !== undefined) params.set("min_confidence", query.min_confidence.toString());
  if (query.max_confidence !== undefined) params.set("max_confidence", query.max_confidence.toString());
  if (query.offset !== undefined) params.set("offset", query.offset.toString());
  if (query.limit !== undefined) params.set("limit", query.limit.toString());

  const res = await apiFetch(`${API_BASE}/api/records?${params}`);
  if (!res.ok) throw new Error("Failed to fetch records");
  return res.json();
}

export async function fetchRecordStats(fileId?: string): Promise<RecordStats> {
  const params = fileId ? `?file_id=${encodeURIComponent(fileId)}` : "";
  const res = await apiFetch(`${API_BASE}/api/records/stats${params}`);
  if (!res.ok) throw new Error("Failed to fetch record stats");
  return res.json();
}

export async function updateRecord(recordId: string, payload: RecordUpdatePayload): Promise<Record_> {
  const res = await apiFetch(`${API_BASE}/api/records/${recordId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error("Failed to update record");
  return res.json();
}

export async function resetRecord(recordId: string): Promise<Record_> {
  const res = await apiFetch(`${API_BASE}/api/records/${recordId}/reset`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to reset record");
  return res.json();
}

export async function bulkUpdateRecords(payload: BulkUpdatePayload): Promise<{ updated: number; requested: number }> {
  const res = await apiFetch(`${API_BASE}/api/records/bulk`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error("Failed to execute bulk update");
  return res.json();
}

export async function createJob(fileIds: string[], templateId = "auto", allPending = false): Promise<Job> {
  const res = await apiFetch(`${API_BASE}/api/jobs`, {
    method: "POST",
    body: JSON.stringify({ file_ids: fileIds, template_id: templateId, all_pending: allPending }),
  });
  if (!res.ok) throw new Error("Failed to submit OCR job");
  return res.json();
}

export async function pauseJobApi(jobId: string): Promise<Job> {
  const res = await apiFetch(`${API_BASE}/api/jobs/${jobId}/pause`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to pause job");
  return res.json();
}

export async function resumeJobApi(jobId: string): Promise<Job> {
  const res = await apiFetch(`${API_BASE}/api/jobs/${jobId}/resume`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to resume job");
  return res.json();
}

export async function cancelJobApi(jobId: string): Promise<Job> {
  const res = await apiFetch(`${API_BASE}/api/jobs/${jobId}/cancel`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to cancel job");
  return res.json();
}

export async function previewExport(req: ExportRequest): Promise<{ columns: string[]; rows: string[][]; total_rows: number }> {
  const res = await apiFetch(`${API_BASE}/api/export/preview`, {
    method: "POST",
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new Error("Failed to preview export");
  return res.json();
}

export async function triggerDownloadExport(req: ExportRequest): Promise<void> {
  const res = await apiFetch(`${API_BASE}/api/export`, {
    method: "POST",
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new Error("Export generation failed");

  const blob = await res.blob();
  const disposition = res.headers.get("Content-Disposition");
  let filename = `ocr-export-${req.mode}.${req.format}`;
  if (disposition && disposition.includes("filename=")) {
    const match = disposition.match(/filename="?([^"]+)"?/);
    if (match && match[1]) filename = match[1];
  }

  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

export async function fetchTemplates(): Promise<TemplateInfo[]> {
  const res = await apiFetch(`${API_BASE}/api/templates`);
  if (!res.ok) throw new Error("Failed to fetch templates");
  return res.json();
}


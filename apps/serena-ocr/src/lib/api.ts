import { FolderPdfItem, FolderScanResponse, Job, SourceFile } from "@/types";

const API_BASE = (
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_API_BASE ||
  ""
).replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public detail?: any
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function apiFetch(url: string, init?: RequestInit): Promise<Response> {
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
    window.dispatchEvent(new CustomEvent("serena:unauthorized"));
  }

  return res;
}

async function handleError(res: Response, fallback: string): Promise<never> {
  let detail: any = "";
  try {
    const json = await res.json();
    detail = json.detail || json.message || JSON.stringify(json);
  } catch {
    detail = await res.text().catch(() => res.statusText);
  }
  throw new ApiError(detail || fallback, res.status, detail);
}

// ---------------------------------------------------------------------------
// Auth APIs
// ---------------------------------------------------------------------------
export async function getAuthStatus(): Promise<{ auth_enabled: boolean; user: any | null }> {
  const res = await apiFetch("/api/auth/status");
  if (!res.ok) await handleError(res, "Failed to fetch auth status");
  return res.json();
}

export async function loginApi(username: string, password: string): Promise<any> {
  const res = await apiFetch("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) await handleError(res, "Login failed");
  return res.json();
}

export async function logoutApi(): Promise<void> {
  await apiFetch("/api/auth/logout", { method: "POST" });
}

// ---------------------------------------------------------------------------
// File & Folder APIs
// ---------------------------------------------------------------------------
export async function scanFolder(path: string, recursive = true): Promise<FolderScanResponse> {
  const res = await apiFetch("/api/files/scan-folder", {
    method: "POST",
    body: JSON.stringify({ path, recursive }),
  });
  if (!res.ok) await handleError(res, "Failed to scan directory");
  return res.json();
}

export async function importFolder(path: string, recursive = true): Promise<SourceFile[]> {
  const res = await apiFetch("/api/files/import-folder", {
    method: "POST",
    body: JSON.stringify({ path, recursive }),
  });
  if (!res.ok) await handleError(res, "Failed to register PDF(s)");
  return res.json();
}

export async function fetchFiles(): Promise<SourceFile[]> {
  const res = await apiFetch("/api/files");
  if (!res.ok) await handleError(res, "Failed to fetch files");
  return res.json();
}

export async function uploadFiles(files: File[]): Promise<SourceFile[]> {
  const formData = new FormData();
  files.forEach((f) => formData.append("files", f));

  const target = `${API_BASE}/api/files`;
  const res = await fetch(target, {
    method: "POST",
    credentials: "include",
    body: formData,
  });
  if (!res.ok) await handleError(res, "Upload failed");
  return res.json();
}

export async function deleteFile(fileId: string): Promise<void> {
  const res = await apiFetch(`/api/files/${fileId}`, { method: "DELETE" });
  if (!res.ok && res.status !== 404) await handleError(res, "Failed to delete file");
}

// ---------------------------------------------------------------------------
// Job Pipeline APIs
// ---------------------------------------------------------------------------
export async function createJob(fileIds: string[], templateId = "auto"): Promise<Job> {
  const res = await apiFetch("/api/jobs", {
    method: "POST",
    body: JSON.stringify({ file_ids: fileIds, template_id: templateId }),
  });
  if (!res.ok) await handleError(res, "Failed to start OCR job");
  return res.json();
}

export async function reprocessFiles(fileIds: string[], templateId = "auto"): Promise<Job> {
  const res = await apiFetch("/api/files/reprocess", {
    method: "POST",
    body: JSON.stringify({ file_ids: fileIds, template_id: templateId }),
  });
  if (!res.ok) await handleError(res, "Failed to re-process files");
  return res.json();
}

export async function cancelJob(jobId: string): Promise<void> {
  const res = await apiFetch(`/api/jobs/${jobId}/cancel`, { method: "POST" });
  if (!res.ok) await handleError(res, "Failed to cancel job");
}

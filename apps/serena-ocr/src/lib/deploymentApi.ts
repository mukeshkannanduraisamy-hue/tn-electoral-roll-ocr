import { apiFetch } from "./api";

export interface SystemStatus {
  status: string;
  uptime_seconds: number;
  uptime_display: string;
  python_version: string;
  platform: string;
  os_name: string;
  cpu_count: number;
  process_pid: number;
  backend_url: string;
  web_url: string;
  serena_url: string;
  ocr_device: string;
  ocr_version: string;
  ocr_workers: number;
  data_dir: string;
  database_path: string;
  database_size_display: string;
  disk_free_gb: number;
  disk_total_gb: number;
  disk_percent_used: number;
}

export interface DiagnosticCheck {
  name: string;
  category: string;
  status: "ok" | "warn" | "fail";
  message: string;
  detail?: string | null;
}

export interface DiagnosticsReport {
  timestamp: number;
  all_passed: boolean;
  checks: DiagnosticCheck[];
}

export async function fetchDeploymentStatus(): Promise<SystemStatus> {
  const res = await apiFetch("/api/deployment/status");
  if (!res.ok) throw new Error("Failed to fetch system deployment status");
  return res.json();
}

export async function runDiagnostics(): Promise<DiagnosticsReport> {
  const res = await apiFetch("/api/deployment/diagnostics");
  if (!res.ok) throw new Error("Diagnostics run failed");
  return res.json();
}

export async function optimizeDatabase(): Promise<{ status: string; message: string; database_size: string }> {
  const res = await apiFetch("/api/deployment/optimize-db", {
    method: "POST",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Database optimization failed" }));
    throw new Error(err.detail || "Database optimization failed");
  }
  return res.json();
}

export async function generateStartupScript(): Promise<{ status: string; message: string; file_path: string }> {
  const res = await apiFetch("/api/deployment/generate-startup-script", {
    method: "POST",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Failed to generate launcher" }));
    throw new Error(err.detail || "Failed to generate launcher");
  }
  return res.json();
}

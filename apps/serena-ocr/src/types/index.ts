export type FileStatus =
  | "unregistered"
  | "pending"
  | "processing"
  | "completed"
  | "error"
  | "cancelled";

export interface FolderPdfItem {
  name: string;
  stored_path: string;
  folder_name: string;
  size_bytes: number;
  page_count: number;
  is_registered: boolean;
  file_id: string | null;
  status: FileStatus;
  pages_done: number;
  records_count: number;
  ocr_duration_sec: number | null;
  error: string | null;
  created_at: string | null;
}

export interface FolderScanResponse {
  folder_path: string;
  folder_name: string;
  total_files: number;
  total_pages: number;
  total_size_bytes: number;
  completed_count: number;
  pending_count: number;
  processing_count: number;
  error_count: number;
  unregistered_count: number;
  items: FolderPdfItem[];
}

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
  stored_path?: string;
  folder_name?: string;
  records_count?: number;
  ocr_duration_sec?: number | null;
}

export interface Job {
  id: string;
  file_ids: string[];
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  total_pages: number;
  completed_pages: number;
  failed_pages: number;
  current_item: string | null;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
}

export interface FileJobProgress {
  fileId: string;
  fileName: string;
  pagesCompleted: number;
  pagesFailed: number;
  pagesTotal: number;
  done: boolean;
}

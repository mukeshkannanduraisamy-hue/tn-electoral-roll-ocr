import { create } from "zustand";
import { Page, Record_, SourceFile, Job } from "@ocr/shared-types";
import {
  fetchFiles,
  fetchRecordStats,
  RecordStats,
  deleteFile as apiDeleteFile,
  createJob,
  reocrPage as apiReocrPage,
  bulkUpdateRecords,
} from "@/lib/api";
import { toast } from "sonner";

import { pauseJobApi, resumeJobApi, cancelJobApi } from "@/lib/api";

export type ViewTab = "dashboard" | "table" | "page" | "review" | "voters" | "settings" | "analytics" | "polling_stations";

// Per-file extraction progress tracked from SSE
export interface FileJobProgress {
  fileId: string;
  fileName: string;
  pagesCompleted: number;
  pagesFailed: number;
  pagesTotal: number;
  done: boolean;
}

export interface ConfirmModalState {
  isOpen: boolean;
  title: string;
  message: string;
  danger?: boolean;
  confirmText?: string;
  onConfirm: () => void | Promise<void>;
}

interface OcrState {
  // Theme state
  theme: "dark" | "light";
  toggleTheme: () => void;
  setTheme: (theme: "dark" | "light") => void;

  // Workspace selections & navigation
  files: SourceFile[];
  activeFileId: string | null;
  activePageId: string | null;
  activeTab: ViewTab;
  recordStats: RecordStats | null;

  // Record selection & hover sync between table and canvas
  hoveredRecordId: string | null;
  selectedRecordId: string | null;

  // Jobs & SSE Progress
  activeJobId: string | null;
  activeJobProgress: number; // 0-100
  activeJobStatus: string | null;
  pagesPerSec: number;
  etaSeconds: number;
  fileJobProgress: Record<string, FileJobProgress>;

  // Per-page refresh tracking (pageId -> isLoading boolean)
  pageRefreshing: Record<string, boolean>;

  // Filters & Search
  searchQuery: string;
  onlyIssuesFilter: boolean;
  onlyEditedFilter: boolean;
  unreviewedFilter: boolean;
  minConfidenceFilter: number | null;
  isUploading: boolean;

  // Modals & Overlays
  isShortcutsOpen: boolean;
  confirmModal: ConfirmModalState | null;
  setConfirmModal: (modal: ConfirmModalState | null) => void;

  // Actions
  loadFiles: () => Promise<void>;
  setActiveFileId: (id: string | null) => void;
  setActivePageId: (id: string | null) => void;
  setActiveTab: (tab: ViewTab) => void;
  setHoveredRecordId: (id: string | null) => void;
  setSelectedRecordId: (id: string | null) => void;
  setSearchQuery: (query: string) => void;
  setOnlyIssuesFilter: (val: boolean) => void;
  setOnlyEditedFilter: (val: boolean) => void;
  setUnreviewedFilter: (val: boolean) => void;
  setMinConfidenceFilter: (val: number | null) => void;
  setIsUploading: (val: boolean) => void;
  setIsShortcutsOpen: (val: boolean) => void;

  refreshStats: (fileId?: string) => Promise<void>;
  deleteFile: (id: string) => Promise<void>;
  setActiveJob: (jobId: string | null, status?: string | null) => void;
  updateJobProgress: (progress: number, status?: string) => void;

  // Job Control Actions
  pauseJob: () => Promise<void>;
  resumeJob: () => Promise<void>;
  cancelJob: () => Promise<void>;

  // Page-by-Page Refresh Action
  reocrSinglePage: (pageId: string, templateId?: string, upscale?: number) => Promise<Page | null>;

  // Bulk Quick Action: Approve all high-confidence clean records
  acceptHighConfidenceRecords: () => Promise<number>;

  // Starts an OCR job for given fileIds
  startBulkJob: (fileIds: string[], templateId?: string, allPending?: boolean) => Promise<Job | null>;
}


// Subscribe to a job's SSE stream and update store state progressively
function attachJobSSE(
  jobId: string,
  get: () => OcrState,
  set: (partial: Partial<OcrState> | ((s: OcrState) => Partial<OcrState>)) => void
) {
  const evtSource = new EventSource(`/api/jobs/${jobId}/events`);

  const handleProgress = (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data);
      const { completed = 0, failed = 0, total = 1, file_id, file_name, pages_per_sec = 0, eta_seconds = 0 } = data;
      const pct = total > 0 ? ((completed + failed) / total) * 100 : 0;

      set((state) => {
        const prev = state.fileJobProgress[file_id] || {
          fileId: file_id,
          fileName: file_name || file_id,
          pagesCompleted: 0,
          pagesFailed: 0,
          pagesTotal: total,
          done: false,
        };
        return {
          activeJobProgress: pct,
          pagesPerSec: pages_per_sec,
          etaSeconds: eta_seconds,
          fileJobProgress: file_id
            ? {
                ...state.fileJobProgress,
                [file_id]: {
                  ...prev,
                  pagesCompleted: completed,
                  pagesFailed: failed,
                  pagesTotal: total,
                },
              }
            : state.fileJobProgress,
        };
      });
    } catch {}
  };

  const handleFileDone = (e: MessageEvent) => {
    try {
      const { file_id } = JSON.parse(e.data);
      set((state) => ({
        fileJobProgress: {
          ...state.fileJobProgress,
          [file_id]: {
            ...(state.fileJobProgress[file_id] || {
              fileId: file_id,
              fileName: file_id,
              pagesCompleted: 0,
              pagesFailed: 0,
              pagesTotal: 0,
            }),
            done: true,
          },
        },
      }));
    } catch {}
  };

  let isDone = false;

  const handleJobDone = (e?: any) => {
    if (isDone) return;
    isDone = true;
    evtSource.close();

    let isFailed = false;
    try {
      if (e?.data) {
        const data = JSON.parse(e.data);
        if (data?.status === "failed") isFailed = true;
      }
    } catch {}

    set({ activeJobId: null, activeJobStatus: isFailed ? "failed" : "completed", activeJobProgress: 100, pagesPerSec: 0, etaSeconds: 0 });
    get().loadFiles();
    get().refreshStats(get().activeFileId || undefined);

    if (isFailed) {
      toast.error("OCR job processing failed");
    } else {
      toast.success("Bulk OCR processing completed!");
    }
    setTimeout(() => set({ fileJobProgress: {} }), 3000);
  };

  const handleError = () => {
    if (isDone) return;
    isDone = true;
    evtSource.close();
    set({ activeJobId: null, activeJobStatus: null, pagesPerSec: 0, etaSeconds: 0 });
    get().loadFiles();
  };

  evtSource.addEventListener("progress", handleProgress);
  evtSource.addEventListener("file_done", handleFileDone);
  evtSource.addEventListener("job_done", handleJobDone);
  evtSource.addEventListener("error", handleError);

  return evtSource;
}

export const useOcrStore = create<OcrState>((set, get) => ({
  theme: "dark",
  toggleTheme: () => {
    const next = get().theme === "dark" ? "light" : "dark";
    if (typeof document !== "undefined") {
      if (next === "dark") {
        document.documentElement.classList.add("dark");
      } else {
        document.documentElement.classList.remove("dark");
      }
    }
    set({ theme: next });
  },
  setTheme: (theme) => {
    if (typeof document !== "undefined") {
      if (theme === "dark") {
        document.documentElement.classList.add("dark");
      } else {
        document.documentElement.classList.remove("dark");
      }
    }
    set({ theme });
  },

  files: [],
  activeFileId: null,
  activePageId: null,
  activeTab: "dashboard",
  recordStats: null,

  hoveredRecordId: null,
  selectedRecordId: null,

  activeJobId: null,
  activeJobProgress: 0,
  activeJobStatus: null,
  pagesPerSec: 0,
  etaSeconds: 0,
  fileJobProgress: {},

  pageRefreshing: {},

  searchQuery: "",
  onlyIssuesFilter: false,
  onlyEditedFilter: false,
  unreviewedFilter: false,
  minConfidenceFilter: null,
  isUploading: false,
  isShortcutsOpen: false,
  confirmModal: null,
  setConfirmModal: (modal) => set({ confirmModal: modal }),

  loadFiles: async () => {
    try {
      const files = await fetchFiles();
      set({ files });
      if (files.length > 0 && !get().activeFileId) {
        set({ activeFileId: files[0].id });
      }
      get().refreshStats(get().activeFileId || undefined);
    } catch (e) {
      console.error("Failed to load files", e);
    }
  },

  setActiveFileId: (id) => {
    set({ activeFileId: id, activePageId: null, selectedRecordId: null, hoveredRecordId: null });
    get().refreshStats(id || undefined);
  },

  setActivePageId: (id) => set({ activePageId: id, selectedRecordId: null }),
  setActiveTab: (tab) => set({ activeTab: tab }),
  setHoveredRecordId: (hoveredRecordId) => set({ hoveredRecordId }),
  setSelectedRecordId: (selectedRecordId) => set({ selectedRecordId }),

  setSearchQuery: (searchQuery) => set({ searchQuery }),
  setOnlyIssuesFilter: (onlyIssuesFilter) => set({ onlyIssuesFilter }),
  setOnlyEditedFilter: (onlyEditedFilter) => set({ onlyEditedFilter }),
  setUnreviewedFilter: (unreviewedFilter) => set({ unreviewedFilter }),
  setMinConfidenceFilter: (minConfidenceFilter) => set({ minConfidenceFilter }),
  setIsUploading: (isUploading) => set({ isUploading }),
  setIsShortcutsOpen: (isShortcutsOpen) => set({ isShortcutsOpen }),

  refreshStats: async (fileId) => {
    try {
      const stats = await fetchRecordStats(fileId);
      set({ recordStats: stats });
    } catch (e) {
      console.error("Failed to refresh record stats", e);
    }
  },

  deleteFile: async (fileId) => {
    try {
      await apiDeleteFile(fileId);
      const files = get().files.filter((f) => f.id !== fileId);
      const nextActive =
        get().activeFileId === fileId ? files[0]?.id || null : get().activeFileId;
      set({ files, activeFileId: nextActive, activePageId: null, selectedRecordId: null });
      get().refreshStats(nextActive || undefined);
      toast.success("Document deleted successfully");
    } catch (e) {
      console.error("Failed to delete file", e);
      toast.error("Failed to delete document");
    }
  },

  setActiveJob: (jobId, status = "queued") => {
    set({ activeJobId: jobId, activeJobStatus: status, activeJobProgress: 0, pagesPerSec: 0, etaSeconds: 0, fileJobProgress: {} });
  },

  updateJobProgress: (progress, status) => {
    set((state) => ({
      activeJobProgress: progress,
      activeJobStatus: status || state.activeJobStatus,
    }));
  },

  pauseJob: async () => {
    const jobId = get().activeJobId;
    if (!jobId) return;
    try {
      await pauseJobApi(jobId);
      set({ activeJobStatus: "paused" });
      toast.info("OCR job paused");
    } catch (e) {
      toast.error("Failed to pause job");
    }
  },

  resumeJob: async () => {
    const jobId = get().activeJobId;
    if (!jobId) return;
    try {
      await resumeJobApi(jobId);
      set({ activeJobStatus: "running" });
      toast.info("OCR job resumed");
    } catch (e) {
      toast.error("Failed to resume job");
    }
  },

  cancelJob: async () => {
    const jobId = get().activeJobId;
    if (!jobId) return;
    try {
      await cancelJobApi(jobId);
      set({ activeJobId: null, activeJobStatus: "cancelled", activeJobProgress: 0, pagesPerSec: 0, etaSeconds: 0 });
      toast.warning("OCR job cancelled");

    } catch (e) {
      toast.error("Failed to cancel job");
    }
  },


  reocrSinglePage: async (pageId, templateId = "auto", upscale = 2.0) => {
    set((state) => ({
      pageRefreshing: { ...state.pageRefreshing, [pageId]: true },
    }));
    toast.info(`Re-running OCR extraction for page ${pageId}...`);
    try {
      const updatedPage = await apiReocrPage(pageId, templateId, upscale);
      get().refreshStats(get().activeFileId || undefined);
      toast.success(`Page re-extracted successfully! (${updatedPage.records.length} records)`);
      return updatedPage;
    } catch (e) {
      console.error("Failed page re-OCR", e);
      toast.error(`Failed to re-run OCR for page ${pageId}`);
      return null;
    } finally {
      set((state) => {
        const next = { ...state.pageRefreshing };
        delete next[pageId];
        return { pageRefreshing: next };
      });
    }
  },

  acceptHighConfidenceRecords: async () => {
    try {
      // Find clean records and bulk approve
      const result = await bulkUpdateRecords({
        record_ids: [],
        reviewed: true,
        accept_suggestions: true,
      });
      get().refreshStats(get().activeFileId || undefined);
      toast.success(`Approved ${result.updated} high-confidence records`);
      return result.updated;
    } catch (e) {
      console.error("Failed to accept high confidence records", e);
      toast.error("Failed to bulk approve records");
      return 0;
    }
  },

  startBulkJob: async (fileIds, templateId = "auto", allPending = false) => {
    try {
      const job = await createJob(fileIds, templateId, allPending);
      set({ activeJobId: job.id, activeJobStatus: "running", activeJobProgress: 0, fileJobProgress: {} });
      attachJobSSE(job.id, get, set as any);
      toast.info(`Started OCR extraction task #${job.id.slice(0, 6)}`);
      return job;
    } catch (e) {
      console.error("Failed to start OCR job", e);
      toast.error("Failed to initiate OCR extraction job");
      return null;
    }
  },
}));

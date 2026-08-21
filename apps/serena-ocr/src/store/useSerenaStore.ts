import { create } from "zustand";
import { FolderPdfItem, FolderScanResponse, SourceFile, FileJobProgress, Job } from "@/types";
import {
  scanFolder as apiScanFolder,
  importFolder as apiImportFolder,
  createJob as apiCreateJob,
  reprocessFiles as apiReprocessFiles,
  cancelJob as apiCancelJob,
  fetchFiles as apiFetchFiles,
  deleteFile as apiDeleteFile,
  getAuthStatus,
  loginApi,
  logoutApi,
} from "@/lib/api";
import { toast } from "sonner";

export interface SerenaState {
  // Auth state
  user: any | null;
  authEnabled: boolean;
  authChecked: boolean;
  checkAuth: () => Promise<void>;
  login: (u: string, p: string) => Promise<boolean>;
  logout: () => Promise<void>;

  // Database Files
  dbFiles: SourceFile[];
  loadDbFiles: () => Promise<void>;

  // Folder Explorer State
  folderPath: string;
  recursive: boolean;
  isScanning: boolean;
  scannedData: FolderScanResponse | null;
  selectedPaths: Set<string>;
  searchQuery: string;
  statusFilter: "all" | "pending" | "completed" | "processing" | "error";
  sortBy: "name" | "size" | "pages" | "status" | "records";
  sortDesc: boolean;
  viewMode: "grid" | "table";
  templateId: string;
  actionInProgress: string | null;

  // Real-time Job State
  activeJobId: string | null;
  activeJobStatus: string | null;
  activeJobProgress: number;
  pagesPerSec: number;
  etaSeconds: number;
  fileJobProgress: Record<string, FileJobProgress>;

  // Theme & Navigation State
  theme: "dark" | "light";
  activeTab: "workstation" | "database" | "deployment";
  autoInsertToDb: boolean;

  // Quantum Studio Active Selection & Elector Stream
  selectedItem: FolderPdfItem | null;
  activePageNumber: number;
  liveExtractedElectors: any[];
  isLoadingElectors: boolean;
  isAutonomousFlowActive: boolean;

  // Setters
  setTheme: (t: "dark" | "light") => void;
  toggleTheme: () => void;
  setActiveTab: (tab: "workstation" | "database" | "deployment") => void;
  toggleAutoInsertToDb: () => void;
  setSelectedItem: (item: FolderPdfItem | null) => void;
  setActivePageNumber: (pg: number) => void;
  setLiveExtractedElectors: (records: any[]) => void;
  setFolderPath: (path: string) => void;
  setRecursive: (val: boolean) => void;
  setSearchQuery: (query: string) => void;
  setStatusFilter: (filter: "all" | "pending" | "completed" | "processing" | "error") => void;
  setSortBy: (sort: "name" | "size" | "pages" | "status" | "records") => void;
  setSortDesc: (val: boolean) => void;
  setViewMode: (mode: "grid" | "table") => void;
  setTemplateId: (id: string) => void;
  toggleSelect: (path: string) => void;
  toggleSelectAll: () => void;
  setScannedData: (data: FolderScanResponse | null) => void;

  // Action Methods
  loadElectorsForFile: (fileId: string) => Promise<void>;
  launchAutonomousFlow: () => Promise<void>;
  scanCurrentFolder: (overridePath?: string) => Promise<void>;
  importEntireFolder: (targetFolder?: string) => Promise<any>;
  ensureRegistered: (item: FolderPdfItem) => Promise<string | null>;
  processSingle: (item: FolderPdfItem) => Promise<void>;
  reprocessSingle: (item: FolderPdfItem) => Promise<void>;
  processSelected: () => Promise<void>;
  reprocessSelected: () => Promise<void>;
  processAllUnprocessed: () => Promise<void>;
  promoteAllToDatabase: () => Promise<void>;
  cancelActiveJob: () => Promise<void>;
  deleteRegisteredFile: (fileId: string) => Promise<void>;
}

function attachJobSSE(
  jobId: string,
  get: () => SerenaState,
  set: (partial: Partial<SerenaState> | ((s: SerenaState) => Partial<SerenaState>)) => void
) {
  const evtSource = new EventSource(`/api/jobs/${jobId}/events`);

  const handleProgress = (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data);
      const {
        completed = 0,
        failed = 0,
        total = 1,
        file_id,
        file_name,
        pages_per_sec = 0,
        eta_seconds = 0,
      } = data;
      const pct = total > 0 ? ((completed + failed) / total) * 100 : 0;
      const fileCompleted = data.file_completed ?? completed;
      const fileFailed = data.file_failed ?? failed;
      const fileTotal = data.file_total ?? total;

      set((state) => {
        const prev = state.fileJobProgress[file_id] || {
          fileId: file_id,
          fileName: file_name || file_id,
          pagesCompleted: 0,
          pagesFailed: 0,
          pagesTotal: total,
          done: false,
        };

        let updatedScanned = state.scannedData;
        if (state.scannedData?.items && file_id) {
          const items = state.scannedData.items.map((item) => {
            if (item.file_id === file_id && item.status !== "completed") {
              return { ...item, status: "processing" as const, pages_done: fileCompleted };
            }
            return item;
          });
          updatedScanned = {
            ...state.scannedData,
            completed_count: items.filter((i) => i.status === "completed").length,
            pending_count: items.filter((i) => i.status === "pending" || i.status === "unregistered").length,
            processing_count: items.filter((i) => i.status === "processing").length,
            error_count: items.filter((i) => i.status === "error").length,
            items,
          };
        }

        return {
          activeJobProgress: pct,
          pagesPerSec: pages_per_sec,
          etaSeconds: eta_seconds,
          scannedData: updatedScanned,
          fileJobProgress: file_id
            ? {
                ...state.fileJobProgress,
                [file_id]: {
                  ...prev,
                  fileName: file_name || prev.fileName,
                  pagesCompleted: fileCompleted,
                  pagesFailed: fileFailed,
                  pagesTotal: fileTotal,
                },
              }
            : state.fileJobProgress,
        };
      });
    } catch {}
  };

  const handleFileDone = (e: MessageEvent) => {
    try {
      const { file_id, records_count } = JSON.parse(e.data);
      set((state) => {
        let updatedScanned = state.scannedData;
        if (state.scannedData?.items && file_id) {
          const items = state.scannedData.items.map((item) => {
            if (item.file_id === file_id) {
              return {
                ...item,
                status: "completed" as const,
                records_count: records_count ?? item.records_count,
              };
            }
            return item;
          });
          updatedScanned = {
            ...state.scannedData,
            completed_count: items.filter((i) => i.status === "completed").length,
            pending_count: items.filter((i) => i.status === "pending" || i.status === "unregistered").length,
            processing_count: items.filter((i) => i.status === "processing").length,
            error_count: items.filter((i) => i.status === "error").length,
            items,
          };
        }

        return {
          scannedData: updatedScanned,
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
        };
      });
      void get().loadDbFiles();
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

    set({
      activeJobId: null,
      activeJobStatus: isFailed ? "failed" : "completed",
      activeJobProgress: 100,
      pagesPerSec: 0,
      etaSeconds: 0,
    });
    void get().loadDbFiles();
    void get().scanCurrentFolder();

    if (isFailed) {
      toast.error("OCR batch processing failed");
    } else {
      toast.success("OCR batch processing completed!");
    }
  };

  const handleError = () => {
    if (isDone) return;
    isDone = true;
    evtSource.close();
    set({ activeJobId: null, activeJobStatus: null, pagesPerSec: 0, etaSeconds: 0 });
    void get().loadDbFiles();
    void get().scanCurrentFolder();
  };

  evtSource.addEventListener("progress", handleProgress);
  evtSource.addEventListener("file_done", handleFileDone);
  evtSource.addEventListener("job_done", handleJobDone);
  evtSource.addEventListener("error", handleError);

  return evtSource;
}

export const useSerenaStore = create<SerenaState>((set, get) => ({
  user: null,
  authEnabled: false,
  authChecked: false,

  checkAuth: async () => {
    try {
      const st = await getAuthStatus();
      set({ user: st.user, authEnabled: st.auth_enabled, authChecked: true });
    } catch {
      set({ user: null, authChecked: true });
    }
  },

  login: async (u: string, p: string) => {
    try {
      const user = await loginApi(u, p);
      set({ user });
      toast.success(`Welcome back, ${user.username || "Admin"}!`);
      await get().loadDbFiles();
      return true;
    } catch (e: any) {
      toast.error(e?.message || "Invalid credentials");
      return false;
    }
  },

  logout: async () => {
    try {
      await logoutApi();
      set({ user: null });
      toast.info("Signed out");
    } catch {}
  },

  dbFiles: [],
  loadDbFiles: async () => {
    try {
      const dbFiles = await apiFetchFiles();
      set({ dbFiles });

      // Merge with active scannedData if present
      const scanned = get().scannedData;
      if (scanned) {
        const dbByPath = new Map<string, SourceFile>();
        const dbByName = new Map<string, SourceFile>();
        dbFiles.forEach((f) => {
          if (f.stored_path) dbByPath.set(f.stored_path, f);
          if (f.name) dbByName.set(f.name, f);
        });

        const updatedItems = scanned.items.map((item) => {
          const dbFile = dbByPath.get(item.stored_path) || dbByName.get(item.name);
          if (dbFile) {
            return {
              ...item,
              is_registered: true,
              file_id: dbFile.id,
              status: dbFile.status,
              pages_done: dbFile.pages_done,
              page_count: dbFile.page_count || item.page_count,
              records_count: dbFile.records_count || item.records_count,
              ocr_duration_sec: dbFile.ocr_duration_sec ?? item.ocr_duration_sec,
              error: dbFile.error ?? item.error,
            };
          }
          return item;
        });

        set({
          scannedData: {
            ...scanned,
            completed_count: updatedItems.filter((i) => i.status === "completed").length,
            pending_count: updatedItems.filter((i) => i.status === "pending").length,
            processing_count: updatedItems.filter((i) => i.status === "processing").length,
            error_count: updatedItems.filter((i) => i.status === "error").length,
            items: updatedItems,
          },
        });
      }
    } catch (e) {
      console.error("Failed to load db files", e);
    }
  },

  folderPath: "D:\\OCR\\PDF\\Penn PDF",
  recursive: false,
  isScanning: false,
  scannedData: null,
  selectedPaths: new Set(),
  searchQuery: "",
  statusFilter: "all",
  sortBy: "name",
  sortDesc: false,
  viewMode: "grid",
  templateId: "auto",
  actionInProgress: null,

  activeJobId: null,
  activeJobStatus: null,
  activeJobProgress: 0,
  pagesPerSec: 0,
  etaSeconds: 0,
  fileJobProgress: {},

  theme: "dark",
  activeTab: "workstation",
  autoInsertToDb: true,

  selectedItem: null,
  activePageNumber: 1,
  liveExtractedElectors: [],
  isLoadingElectors: false,
  isAutonomousFlowActive: false,

  setTheme: (theme) => {
    if (typeof window !== "undefined") {
      localStorage.setItem("serena-theme", theme);
      if (theme === "dark") {
        document.documentElement.classList.add("dark");
      } else {
        document.documentElement.classList.remove("dark");
      }
    }
    set({ theme });
  },

  toggleTheme: () => {
    const nextTheme = get().theme === "dark" ? "light" : "dark";
    get().setTheme(nextTheme);
  },

  setActiveTab: (activeTab) => set({ activeTab }),
  toggleAutoInsertToDb: () => set((s) => ({ autoInsertToDb: !s.autoInsertToDb })),

  setSelectedItem: (selectedItem) => {
    set({ selectedItem, activePageNumber: 1 });
    if (selectedItem?.file_id) {
      void get().loadElectorsForFile(selectedItem.file_id);
    } else {
      set({ liveExtractedElectors: [] });
    }
  },

  setActivePageNumber: (activePageNumber) => set({ activePageNumber }),
  setLiveExtractedElectors: (liveExtractedElectors) => set({ liveExtractedElectors }),

  loadElectorsForFile: async (fileId: string) => {
    set({ isLoadingElectors: true });
    try {
      const res = await fetch(`/api/records?file_id=${encodeURIComponent(fileId)}&limit=1000`);
      if (res.ok) {
        const data = await res.json();
        set({ liveExtractedElectors: data.items || [] });
      }
    } catch (e) {
      console.warn("Failed to fetch electors for file", fileId, e);
    } finally {
      set({ isLoadingElectors: false });
    }
  },

  launchAutonomousFlow: async () => {
    const { scannedData, processAllUnprocessed } = get();
    if (!scannedData?.items || scannedData.items.length === 0) {
      toast.error("No documents discovered. Scan a folder first.");
      return;
    }
    set({ isAutonomousFlowActive: true });
    toast.info("⚡ Autonomous Quantum Flow Initiated: Processing all pending parts...");
    try {
      await processAllUnprocessed();
      toast.success("✨ Autonomous Flow complete! All voter records curated and auto-promoted.");
    } catch (e: any) {
      toast.error(e?.message || "Autonomous flow halted");
    } finally {
      set({ isAutonomousFlowActive: false });
    }
  },

  setFolderPath: (folderPath) => set({ folderPath }),
  setRecursive: (recursive) => set({ recursive }),
  setSearchQuery: (searchQuery) => set({ searchQuery }),
  setStatusFilter: (statusFilter) => set({ statusFilter }),
  setSortBy: (sortBy) => set({ sortBy }),
  setSortDesc: (sortDesc) => set({ sortDesc }),
  setViewMode: (viewMode) => set({ viewMode }),
  setTemplateId: (templateId) => set({ templateId }),
  setScannedData: (scannedData) => {
    const prevSelected = get().selectedItem;
    let nextSelected = prevSelected;
    if (scannedData?.items && scannedData.items.length > 0) {
      if (!prevSelected || !scannedData.items.some((i) => i.stored_path === prevSelected.stored_path)) {
        nextSelected = scannedData.items[0];
      }
    }
    set({ scannedData, selectedItem: nextSelected });
    if (nextSelected?.file_id) {
      void get().loadElectorsForFile(nextSelected.file_id);
    }
  },

  promoteAllToDatabase: async () => {
    try {
      toast.info("Promoting all OCR records into curated voters database...");
      const res = await fetch("/api/voters/promote-all", { method: "POST" });
      if (!res.ok) throw new Error("Failed to promote records");
      const data = await res.json();
      toast.success(
        `Database updated! ${data.created} created, ${data.updated} updated, ${data.skipped} skipped.`
      );
      await get().loadDbFiles();
    } catch (e: any) {
      toast.error(e?.message || "Failed to promote records into database");
    }
  },

  toggleSelect: (path) => {
    set((state) => {
      const next = new Set(state.selectedPaths);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return { selectedPaths: next };
    });
  },

  toggleSelectAll: () => {
    const { scannedData, selectedPaths } = get();
    if (!scannedData?.items) return;
    if (selectedPaths.size === scannedData.items.length && scannedData.items.length > 0) {
      set({ selectedPaths: new Set() });
    } else {
      set({ selectedPaths: new Set(scannedData.items.map((i) => i.stored_path)) });
    }
  },

  scanCurrentFolder: async (overridePath?: string) => {
    const targetPath = (overridePath || get().folderPath).trim();
    if (!targetPath) {
      toast.error("Please enter or select a valid folder path");
      return;
    }
    set({ isScanning: true, folderPath: targetPath });
    try {
      const res = await apiScanFolder(targetPath, get().recursive);
      set({ scannedData: res });
      // Pre-select pending & unregistered files
      const pendingPaths = res.items
        .filter((item) => item.status === "pending" || item.status === "unregistered")
        .map((item) => item.stored_path);
      set({ selectedPaths: new Set(pendingPaths) });
      toast.success(`Discovered ${res.total_files} PDF documents`);
    } catch (e: any) {
      toast.error(e?.message || "Failed to scan folder");
    } finally {
      set({ isScanning: false });
    }
  },

  ensureRegistered: async (item: FolderPdfItem) => {
    if (item.file_id) return item.file_id;
    try {
      const imported = await apiImportFolder(item.stored_path, false);
      const match =
        imported.find((f) => f.name === item.name || f.stored_path === item.stored_path) ||
        imported[0];
      if (match?.id) {
        item.file_id = match.id;
        item.is_registered = true;
        await get().loadDbFiles();
        return match.id;
      }
      return null;
    } catch (e: any) {
      toast.error(`Could not register ${item.name}: ${e?.message}`);
      return null;
    }
  },

  processSingle: async (item: FolderPdfItem) => {
    set({ actionInProgress: item.stored_path });
    try {
      let fileId = item.file_id;
      if (!fileId) {
        toast.info(`Registering ${item.name}...`);
        fileId = await get().ensureRegistered(item);
      }
      if (!fileId) throw new Error("Could not register PDF");

      const job = await apiCreateJob([fileId], get().templateId);
      set({ activeJobId: job.id, activeJobStatus: "running", activeJobProgress: 0, fileJobProgress: {} });
      attachJobSSE(job.id, get, set as any);
      toast.info(`Started OCR task for ${item.name}`);
    } catch (e: any) {
      toast.error(e?.message || "Failed to initiate OCR");
    } finally {
      set({ actionInProgress: null });
    }
  },

  reprocessSingle: async (item: FolderPdfItem) => {
    if (!item.file_id) return;
    set({ actionInProgress: item.stored_path });
    try {
      const job = await apiReprocessFiles([item.file_id], get().templateId);
      set({ activeJobId: job.id, activeJobStatus: "running", activeJobProgress: 0, fileJobProgress: {} });
      attachJobSSE(job.id, get, set as any);
      toast.info(`Re-processing started for ${item.name}`);
    } catch (e: any) {
      toast.error(e?.message || "Failed to re-process");
    } finally {
      set({ actionInProgress: null });
    }
  },

  importEntireFolder: async (targetFolder?: string) => {
    const folder = (targetFolder || get().folderPath).trim();
    if (!folder) return [];
    try {
      const imported = await apiImportFolder(folder, get().recursive);
      const idMap = new Map(imported.map((f) => [f.stored_path, f.id]));
      set((state) => {
        if (!state.scannedData?.items) return {};
        const items = state.scannedData.items.map((item) => {
          const fid = idMap.get(item.stored_path) || item.file_id;
          return {
            ...item,
            file_id: fid,
            is_registered: !!fid,
          };
        });
        return {
          scannedData: { ...state.scannedData, items },
        };
      });
      await get().loadDbFiles();
      return imported;
    } catch (e: any) {
      toast.error(`Could not bulk register folder: ${e?.message}`);
      return [];
    }
  },

  processSelected: async () => {
    const { scannedData, selectedPaths, templateId } = get();
    if (!scannedData || selectedPaths.size === 0) return;
    const selectedItems = scannedData.items.filter((i) => selectedPaths.has(i.stored_path));
    if (selectedItems.length === 0) return;

    set({ actionInProgress: "batch" });
    toast.info(`Preparing ${selectedItems.length} PDF(s)...`);
    try {
      // Bulk register if any are missing file_id
      const hasUnregistered = selectedItems.some((i) => !i.file_id);
      if (hasUnregistered) {
        await get().importEntireFolder(get().folderPath);
      }

      const refreshedData = get().scannedData;
      const currentSelected = refreshedData?.items.filter((i) => selectedPaths.has(i.stored_path)) || [];
      const fileIds = currentSelected.map((i) => i.file_id).filter(Boolean) as string[];

      if (fileIds.length > 0) {
        const job = await apiCreateJob(fileIds, templateId);
        set({ activeJobId: job.id, activeJobStatus: "running", activeJobProgress: 0, fileJobProgress: {} });
        attachJobSSE(job.id, get, set as any);
        toast.info(`Queued ${fileIds.length} PDFs for OCR extraction`);
      }
    } catch (e: any) {
      toast.error(e?.message || "Batch process failed");
    } finally {
      set({ actionInProgress: null });
    }
  },

  reprocessSelected: async () => {
    const { scannedData, selectedPaths, templateId } = get();
    if (!scannedData || selectedPaths.size === 0) return;
    const completedItems = scannedData.items.filter(
      (i) => selectedPaths.has(i.stored_path) && (i.status === "completed" || i.status === "error") && i.file_id
    );
    if (completedItems.length === 0) {
      toast.warning("No completed or error files selected for re-processing");
      return;
    }

    const fileIds = completedItems.map((i) => i.file_id!);
    set({ actionInProgress: "batch_reprocess" });
    try {
      const job = await apiReprocessFiles(fileIds, templateId);
      set({ activeJobId: job.id, activeJobStatus: "running", activeJobProgress: 0, fileJobProgress: {} });
      attachJobSSE(job.id, get, set as any);
      toast.info(`Re-processing ${fileIds.length} files`);
    } catch (e: any) {
      toast.error(e?.message || "Bulk re-process failed");
    } finally {
      set({ actionInProgress: null });
    }
  },

  processAllUnprocessed: async () => {
    const { scannedData, templateId } = get();
    if (!scannedData || scannedData.items.length === 0) return;
    const pendingItems = scannedData.items.filter(
      (i) => i.status === "pending" || i.status === "unregistered" || i.status === "error"
    );
    if (pendingItems.length === 0) {
      toast.info("All PDFs in this folder are already processed!");
      return;
    }

    set({ actionInProgress: "all_pending" });
    toast.info(`Registering & queueing ${pendingItems.length} unprocessed PDFs...`);
    try {
      // Bulk register all items in 1 network request
      await get().importEntireFolder(get().folderPath);

      const refreshedData = get().scannedData;
      const currentPending = refreshedData?.items.filter(
        (i) => i.status === "pending" || i.status === "unregistered" || i.status === "error"
      ) || [];
      const fileIds = currentPending.map((i) => i.file_id).filter(Boolean) as string[];

      if (fileIds.length > 0) {
        const job = await apiCreateJob(fileIds, templateId);
        set({ activeJobId: job.id, activeJobStatus: "running", activeJobProgress: 0, fileJobProgress: {} });
        attachJobSSE(job.id, get, set as any);
        toast.info(`Started batch processing for ${fileIds.length} PDFs`);
      }
    } catch (e: any) {
      toast.error(e?.message || "Process all failed");
    } finally {
      set({ actionInProgress: null });
    }
  },

  cancelActiveJob: async () => {
    const { activeJobId } = get();
    if (!activeJobId) return;
    try {
      await apiCancelJob(activeJobId);
      set({ activeJobId: null, activeJobStatus: "cancelled" });
      toast.info("Job cancelled");
    } catch (e: any) {
      toast.error(e?.message || "Failed to cancel");
    }
  },

  deleteRegisteredFile: async (fileId: string) => {
    try {
      await apiDeleteFile(fileId);
      const { scannedData } = get();
      if (scannedData) {
        const updatedItems = scannedData.items.map((item) => {
          if (item.file_id === fileId) {
            return {
              ...item,
              file_id: null,
              is_registered: false,
              status: "unregistered" as const,
              pages_done: 0,
              records_count: 0,
            };
          }
          return item;
        });
        set({
          scannedData: {
            ...scannedData,
            completed_count: updatedItems.filter((i) => i.status === "completed").length,
            pending_count: updatedItems.filter((i) => i.status === "pending" || i.status === "unregistered").length,
            processing_count: updatedItems.filter((i) => i.status === "processing").length,
            error_count: updatedItems.filter((i) => i.status === "error").length,
            items: updatedItems,
          },
        });
      }
      await get().loadDbFiles();
      toast.success("Document deleted from database");
    } catch (e: any) {
      toast.error(e?.message || "Failed to delete document");
    }
  },
}));

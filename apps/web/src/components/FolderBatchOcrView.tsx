"use client";

import React, { useState, useEffect, useMemo, useRef } from "react";
import {
  Folder,
  FolderOpen,
  FileText,
  Play,
  RotateCcw,
  RefreshCw,
  Search,
  CheckCircle2,
  AlertTriangle,
  Clock,
  Loader2,
  Zap,
  Layers,
  Sparkles,
  Download,
  Eye,
  Trash2,
  Table as TableIcon,
  LayoutGrid,
  CheckSquare,
  Square,
  ArrowUpDown,
  Filter,
  Users,
  HardDrive,
  Check,
  ChevronRight,
  ExternalLink,
} from "lucide-react";
import { useOcrStore, FileJobProgress } from "@/store/useOcrStore";
import { FolderPdfItem, FolderScanResponse, SourceFile } from "@ocr/shared-types";
import { scanFolder, importFolder, createJob, uploadFiles } from "@/lib/api";
import { toast } from "sonner";

const PRESET_FOLDERS = [
  { label: "Penn PDF (47 Parts)", path: "D:\\OCR\\PDF\\Penn PDF" },
  { label: "Part 10", path: "D:\\OCR\\PDF\\2026-EROLLGEN-S22-57-SIR-FinalRoll-Revision1-TAM-10-WI" },
  { label: "Part 11", path: "D:\\OCR\\PDF\\2026-EROLLGEN-S22-57-SIR-FinalRoll-Revision1-TAM-11-WI" },
  { label: "Part 12", path: "D:\\OCR\\PDF\\2026-EROLLGEN-S22-57-SIR-FinalRoll-Revision1-TAM-12-WI" },
  { label: "Part 13", path: "D:\\OCR\\PDF\\2026-EROLLGEN-S22-57-SIR-FinalRoll-Revision1-TAM-13-WI" },
  { label: "Part 14", path: "D:\\OCR\\PDF\\2026-EROLLGEN-S22-57-SIR-FinalRoll-Revision1-TAM-14-WI" },
  { label: "All PDF Root", path: "D:\\OCR\\PDF" },
];

export const FolderBatchOcrView: React.FC = () => {
  const {
    files,
    loadFiles,
    activeFolder,
    setActiveFolder,
    activeJobId,
    activeJobStatus,
    activeJobProgress,
    pagesPerSec,
    etaSeconds,
    fileJobProgress,
    startBulkJob,
    reprocessFile,
    reprocessBulkFiles,
    setActiveFileId,
    setActiveTab,
    deleteFile,
    setConfirmModal,
  } = useOcrStore();

  const [folderPathInput, setFolderPathInput] = useState(activeFolder || "D:\\OCR\\PDF\\Penn PDF");
  const [recursive, setRecursive] = useState(false);
  const [isScanning, setIsScanning] = useState(false);
  const [scannedData, setScannedData] = useState<FolderScanResponse | null>(null);
  const [selectedPaths, setSelectedPaths] = useState<Set<string>>(new Set());
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "pending" | "completed" | "processing" | "error">("all");
  const [sortBy, setSortBy] = useState<"name" | "size" | "pages" | "status" | "records">("name");
  const [sortDesc, setSortDesc] = useState(false);
  const [viewMode, setViewMode] = useState<"grid" | "table">("grid");
  const [templateId, setTemplateId] = useState("auto");
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Scan folder function
  const handleScan = async (pathOverride?: string) => {
    const targetPath = (pathOverride || folderPathInput).trim();
    if (!targetPath) {
      toast.error("Please enter or select a valid folder path");
      return;
    }
    setIsScanning(true);
    try {
      const res = await scanFolder(targetPath, recursive);
      setScannedData(res);
      setActiveFolder(targetPath);
      // Auto-select pending items
      const pendingPaths = res.items
        .filter((item) => item.status === "pending" || item.status === "unregistered")
        .map((item) => item.stored_path);
      setSelectedPaths(new Set(pendingPaths));
      toast.success(`Found ${res.total_files} PDF files in folder`);
    } catch (e: any) {
      console.error("Scan folder error:", e);
      toast.error(e?.message || "Failed to scan folder");
    } finally {
      setIsScanning(false);
    }
  };

  // Initial scan on mount or when activeFolder changes
  useEffect(() => {
    if (folderPathInput) {
      void handleScan(folderPathInput);
    }
  }, []);

  // When files in DB change, refresh scan data overlay if matching folder
  useEffect(() => {
    if (scannedData) {
      // Cross reference scannedData with updated store files
      const dbByPath = new Map<string, SourceFile>();
      const dbByName = new Map<string, SourceFile>();
      files.forEach((f) => {
        if (f.stored_path) dbByPath.set(f.stored_path, f);
        if (f.name) dbByName.set(f.name, f);
      });

      const updatedItems = scannedData.items.map((item) => {
        const dbFile = dbByPath.get(item.stored_path) || dbByName.get(item.name);
        if (dbFile) {
          return {
            ...item,
            is_registered: true,
            file_id: dbFile.id,
            status: dbFile.status as any,
            pages_done: dbFile.pages_done,
            page_count: dbFile.page_count || item.page_count,
            records_count: dbFile.records_count || item.records_count,
            ocr_duration_sec: dbFile.ocr_duration_sec ?? item.ocr_duration_sec,
            error: dbFile.error ?? item.error,
          };
        }
        return item;
      });

      const completed = updatedItems.filter((i) => i.status === "completed").length;
      const pending = updatedItems.filter((i) => i.status === "pending").length;
      const processing = updatedItems.filter((i) => i.status === "processing").length;
      const error = updatedItems.filter((i) => i.status === "error").length;

      setScannedData({
        ...scannedData,
        completed_count: completed,
        pending_count: pending,
        processing_count: processing,
        error_count: error,
        items: updatedItems,
      });
    }
  }, [files]);

  // Handle client-side folder upload via directory picker
  const handleDirectorySelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = e.target.files;
    if (!selectedFiles || selectedFiles.length === 0) return;

    const pdfFiles = Array.from(selectedFiles).filter((f) =>
      f.name.toLowerCase().endsWith(".pdf")
    );

    if (pdfFiles.length === 0) {
      toast.error("No PDF files found in the chosen folder");
      return;
    }

    toast.info(`Importing ${pdfFiles.length} PDF(s) from selected local directory...`);
    setIsScanning(true);
    try {
      const registered = await uploadFiles(pdfFiles);
      await loadFiles();
      toast.success(`Successfully uploaded and registered ${registered.length} PDFs!`);
      // Update view with uploaded files
      const items: FolderPdfItem[] = registered.map((f) => ({
        name: f.name,
        stored_path: f.stored_path || f.name,
        folder_name: "Uploaded Folder",
        size_bytes: f.size_bytes,
        page_count: f.page_count,
        is_registered: true,
        file_id: f.id,
        status: f.status as any,
        pages_done: f.pages_done,
        records_count: f.records_count || 0,
        ocr_duration_sec: f.ocr_duration_sec || null,
        error: f.error || null,
        created_at: f.created_at,
      }));

      setScannedData({
        folder_path: "Local Client Directory",
        folder_name: "Selected Folder",
        total_files: items.length,
        total_pages: items.reduce((acc, i) => acc + i.page_count, 0),
        total_size_bytes: items.reduce((acc, i) => acc + i.size_bytes, 0),
        completed_count: items.filter((i) => i.status === "completed").length,
        pending_count: items.filter((i) => i.status === "pending").length,
        processing_count: items.filter((i) => i.status === "processing").length,
        error_count: items.filter((i) => i.status === "error").length,
        unregistered_count: 0,
        items,
      });
      setSelectedPaths(new Set(items.map((i) => i.stored_path)));
    } catch (err: any) {
      toast.error(err?.message || "Failed to process folder upload");
    } finally {
      setIsScanning(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  // Helper to ensure file is registered, returning its file_id
  const ensureRegistered = async (item: FolderPdfItem): Promise<string | null> => {
    if (item.file_id) return item.file_id;
    try {
      const imported = await importFolder(item.stored_path, false);
      const match =
        imported.find((f) => f.name === item.name || f.stored_path === item.stored_path) ||
        imported[0];
      if (match?.id) {
        item.file_id = match.id;
        item.is_registered = true;
        await loadFiles();
        return match.id;
      }
      return null;
    } catch (e: any) {
      console.error(`Failed to register ${item.name}:`, e);
      toast.error(`Failed to register ${item.name}: ${e?.message || e}`);
      return null;
    }
  };

  // Process single PDF (Play / Start OCR)
  const handleProcessSingle = async (item: FolderPdfItem) => {
    setActionInProgress(item.stored_path);
    try {
      let fileId = item.file_id;
      if (!fileId) {
        toast.info(`Registering ${item.name}...`);
        fileId = await ensureRegistered(item);
      }
      if (!fileId) throw new Error("Could not register file for processing");

      await startBulkJob([fileId], templateId);
    } catch (e: any) {
      toast.error(e?.message || "Failed to start processing");
    } finally {
      setActionInProgress(null);
    }
  };

  // Re-Process single PDF (Re-run OCR)
  const handleReprocessSingle = async (item: FolderPdfItem) => {
    if (!item.file_id) return;
    setActionInProgress(item.stored_path);
    try {
      await reprocessFile(item.file_id, templateId);
    } catch (e: any) {
      toast.error(e?.message || "Failed to re-process file");
    } finally {
      setActionInProgress(null);
    }
  };

  // Process selected files
  const handleProcessSelected = async () => {
    if (selectedPaths.size === 0) return;
    const selectedItems = (scannedData?.items || []).filter((i) => selectedPaths.has(i.stored_path));
    if (selectedItems.length === 0) return;

    setActionInProgress("batch");
    toast.info(`Preparing to process ${selectedItems.length} PDF(s)...`);
    try {
      const fileIds: string[] = [];
      for (const item of selectedItems) {
        if (item.file_id) {
          fileIds.push(item.file_id);
        } else {
          const fid = await ensureRegistered(item);
          if (fid) fileIds.push(fid);
        }
      }

      if (fileIds.length === 0) {
        toast.error("No valid files could be registered for OCR");
        return;
      }

      await startBulkJob(fileIds, templateId);
    } catch (e: any) {
      toast.error(e?.message || "Failed to batch process");
    } finally {
      setActionInProgress(null);
    }
  };

  // Re-Process all selected completed files
  const handleReprocessSelected = async () => {
    if (selectedPaths.size === 0) return;
    const completedItems = (scannedData?.items || []).filter(
      (i) => selectedPaths.has(i.stored_path) && (i.status === "completed" || i.status === "error") && i.file_id
    );
    if (completedItems.length === 0) {
      toast.warning("None of the selected files are in a completed or error state for re-processing");
      return;
    }

    const fileIds = completedItems.map((i) => i.file_id!);
    setActionInProgress("batch_reprocess");
    try {
      await reprocessBulkFiles(fileIds, templateId);
    } catch (e: any) {
      toast.error(e?.message || "Failed to batch re-process");
    } finally {
      setActionInProgress(null);
    }
  };

  // Process all unprocessed in the folder
  const handleProcessAllUnprocessed = async () => {
    if (!scannedData || scannedData.items.length === 0) return;
    const pendingItems = scannedData.items.filter(
      (i) => i.status === "pending" || i.status === "unregistered" || i.status === "error"
    );
    if (pendingItems.length === 0) {
      toast.info("All PDFs in this folder are already completed!");
      return;
    }

    setActionInProgress("all_pending");
    toast.info(`Preparing ${pendingItems.length} unprocessed PDF(s)...`);
    try {
      const fileIds: string[] = [];
      for (const item of pendingItems) {
        if (item.file_id) {
          fileIds.push(item.file_id);
        } else {
          const fid = await ensureRegistered(item);
          if (fid) fileIds.push(fid);
        }
      }
      if (fileIds.length > 0) {
        await startBulkJob(fileIds, templateId);
      }
    } catch (e: any) {
      toast.error(e?.message || "Batch process failed");
    } finally {
      setActionInProgress(null);
    }
  };

  // Toggle selection
  const toggleSelect = (path: string) => {
    setSelectedPaths((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  // Select all / Deselect all
  const toggleSelectAll = () => {
    if (selectedPaths.size === filteredItems.length && filteredItems.length > 0) {
      setSelectedPaths(new Set());
    } else {
      setSelectedPaths(new Set(filteredItems.map((i) => i.stored_path)));
    }
  };

  // Filter & Sort Items
  const filteredItems = useMemo(() => {
    if (!scannedData?.items) return [];
    return scannedData.items
      .filter((item) => {
        // Search query
        if (searchQuery.trim()) {
          const q = searchQuery.toLowerCase();
          const matchesName = item.name.toLowerCase().includes(q);
          const matchesFolder = item.folder_name.toLowerCase().includes(q);
          if (!matchesName && !matchesFolder) return false;
        }
        // Status filter
        if (statusFilter === "all") return true;
        if (statusFilter === "pending") return item.status === "pending" || item.status === "unregistered";
        if (statusFilter === "completed") return item.status === "completed";
        if (statusFilter === "processing") return item.status === "processing";
        if (statusFilter === "error") return item.status === "error";
        return true;
      })
      .sort((a, b) => {
        let diff = 0;
        if (sortBy === "name") diff = a.name.localeCompare(b.name, undefined, { numeric: true });
        else if (sortBy === "size") diff = a.size_bytes - b.size_bytes;
        else if (sortBy === "pages") diff = a.page_count - b.page_count;
        else if (sortBy === "records") diff = a.records_count - b.records_count;
        else if (sortBy === "status") diff = a.status.localeCompare(b.status);
        return sortDesc ? -diff : diff;
      });
  }, [scannedData, searchQuery, statusFilter, sortBy, sortDesc]);

  // Aggregate stats
  const totalFolderMb = useMemo(() => {
    const bytes = scannedData?.total_size_bytes || 0;
    return (bytes / (1024 * 1024)).toFixed(1);
  }, [scannedData]);

  const totalExtractedRecords = useMemo(() => {
    return (scannedData?.items || []).reduce((acc, i) => acc + (i.records_count || 0), 0);
  }, [scannedData]);

  const isJobRunning = activeJobStatus === "running";

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-slate-950/40 text-slate-100 min-w-0">
      {/* Top Header & Breadcrumb */}
      <div className="px-6 py-4 border-b border-white/5 bg-slate-900/60 backdrop-blur-xl flex flex-col gap-3 shrink-0">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-indigo-500 via-purple-500 to-pink-500 p-0.5 shadow-lg shadow-indigo-500/20">
              <div className="w-full h-full bg-slate-950 rounded-[14px] flex items-center justify-center">
                <Layers className="w-5 h-5 text-indigo-400" />
              </div>
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-base font-black text-white tracking-tight">
                  Folder Explorer & PDF Batch Pipeline
                </h1>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-indigo-500/10 border border-indigo-500/30 text-indigo-400 uppercase tracking-wider">
                  Serena UI
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                Scan local directories, visualize detailed PDF metadata, and trigger live batch OCR / Re-processing
              </p>
            </div>
          </div>

          {/* Quick Stats Pill */}
          {scannedData && (
            <div className="flex items-center gap-2 bg-slate-950/60 border border-white/5 px-3 py-1.5 rounded-xl text-xs font-mono">
              <span className="text-slate-400">Total:</span>
              <span className="font-bold text-white">{scannedData.total_files} PDFs</span>
              <span className="text-slate-600">·</span>
              <span className="font-bold text-indigo-400">{scannedData.total_pages} pgs</span>
              <span className="text-slate-600">·</span>
              <span className="font-bold text-emerald-400">{scannedData.completed_count} Done</span>
              <span className="text-slate-600">·</span>
              <span className="font-bold text-amber-400">{scannedData.pending_count + scannedData.unregistered_count} Pending</span>
            </div>
          )}
        </div>

        {/* Folder Path Bar & Selector */}
        <div className="flex items-center gap-2 flex-wrap pt-1">
          <div className="relative flex-1 min-w-[280px]">
            <Folder className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-indigo-400 pointer-events-none" />
            <input
              type="text"
              value={folderPathInput}
              onChange={(e) => setFolderPathInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void handleScan();
              }}
              placeholder="e.g. D:\OCR\PDF\Penn PDF or /path/to/electoral/rolls"
              className="w-full pl-9 pr-4 py-2 bg-slate-950/80 border border-white/10 rounded-xl text-xs font-mono text-slate-200 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-500/60 transition-all shadow-inner"
            />
          </div>

          <label className="flex items-center gap-2 px-3 py-2 rounded-xl bg-slate-950/60 border border-white/10 text-xs text-slate-300 font-medium cursor-pointer hover:bg-slate-900 transition-colors">
            <input
              type="checkbox"
              checked={recursive}
              onChange={(e) => setRecursive(e.target.checked)}
              className="rounded border-slate-700 text-indigo-600 focus:ring-0 cursor-pointer"
            />
            <span>Subfolders</span>
          </label>

          <button
            onClick={() => void handleScan()}
            disabled={isScanning}
            className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs font-bold flex items-center gap-2 shadow-lg shadow-indigo-600/30 transition-all active:scale-95"
          >
            {isScanning ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
            <span>{isScanning ? "Scanning…" : "Scan Folder"}</span>
          </button>

          {/* Hidden folder upload input for browser picker */}
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleDirectorySelect}
            // @ts-ignore
            webkitdirectory="true"
            directory="true"
            multiple
            className="hidden"
          />

          <button
            onClick={() => fileInputRef.current?.click()}
            className="px-3.5 py-2 rounded-xl bg-slate-800/80 hover:bg-slate-700/80 border border-white/10 text-slate-200 text-xs font-semibold flex items-center gap-1.5 transition-all shadow-sm"
            title="Browse folder directly from your local machine via file explorer"
          >
            <FolderOpen className="w-3.5 h-3.5 text-amber-400" />
            <span className="hidden sm:inline">Browse Folder</span>
          </button>
        </div>

        {/* Preset Folder Chips */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 text-xs no-scrollbar">
          <span className="text-[11px] text-slate-500 font-semibold uppercase tracking-wider shrink-0 mr-1">
            Quick Locations:
          </span>
          {PRESET_FOLDERS.map((preset) => {
            const isSelected = activeFolder === preset.path;
            return (
              <button
                key={preset.path}
                onClick={() => {
                  setFolderPathInput(preset.path);
                  void handleScan(preset.path);
                }}
                className={`px-2.5 py-1 rounded-lg text-xs font-medium whitespace-nowrap transition-all flex items-center gap-1.5 ${
                  isSelected
                    ? "bg-indigo-600/20 text-indigo-300 border border-indigo-500/40 shadow-sm"
                    : "bg-slate-900/60 hover:bg-slate-800 text-slate-400 hover:text-slate-200 border border-white/5"
                }`}
              >
                <Folder className="w-3 h-3 text-indigo-400/80" />
                {preset.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Serena Summary Metric Tiles */}
      {scannedData && (
        <div className="px-6 py-3 grid grid-cols-2 sm:grid-cols-4 gap-3 bg-slate-900/30 border-b border-white/5 shrink-0">
          <div className="card-vimc p-3 rounded-2xl flex items-center gap-3 bg-slate-950/40 border border-white/5">
            <div className="w-9 h-9 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center shrink-0">
              <HardDrive className="w-4 h-4 text-indigo-400" />
            </div>
            <div className="min-w-0">
              <div className="text-[11px] text-slate-400 font-medium">Total Size & Files</div>
              <div className="text-sm font-bold text-white truncate">
                {scannedData.total_files} PDFs <span className="text-xs text-slate-400 font-normal">({totalFolderMb} MB)</span>
              </div>
            </div>
          </div>

          <div className="card-vimc p-3 rounded-2xl flex items-center gap-3 bg-slate-950/40 border border-white/5">
            <div className="w-9 h-9 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center shrink-0">
              <FileText className="w-4 h-4 text-amber-400" />
            </div>
            <div className="min-w-0">
              <div className="text-[11px] text-slate-400 font-medium">Total Pages</div>
              <div className="text-sm font-bold text-white truncate">
                {scannedData.total_pages.toLocaleString()} Pages
              </div>
            </div>
          </div>

          <div className="card-vimc p-3 rounded-2xl flex items-center gap-3 bg-slate-950/40 border border-white/5">
            <div className="w-9 h-9 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center shrink-0">
              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            </div>
            <div className="min-w-0">
              <div className="text-[11px] text-slate-400 font-medium">Completed / Pending</div>
              <div className="text-sm font-bold text-emerald-400 truncate">
                {scannedData.completed_count}{" "}
                <span className="text-xs text-slate-400 font-normal">/ {scannedData.pending_count + scannedData.unregistered_count} pending</span>
              </div>
            </div>
          </div>

          <div className="card-vimc p-3 rounded-2xl flex items-center gap-3 bg-slate-950/40 border border-white/5">
            <div className="w-9 h-9 rounded-xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-center shrink-0">
              <Users className="w-4 h-4 text-purple-400" />
            </div>
            <div className="min-w-0">
              <div className="text-[11px] text-slate-400 font-medium">Extracted Voters</div>
              <div className="text-sm font-bold text-purple-300 truncate">
                {totalExtractedRecords.toLocaleString()} Records
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col overflow-hidden p-6 gap-4 min-h-0">
        {/* Batch Actions & Filtering Toolbar */}
        <div className="flex items-center justify-between gap-3 flex-wrap bg-slate-900/60 p-3 rounded-2xl border border-white/5 shrink-0">
          {/* Left: Selection, Search, and Status Tabs */}
          <div className="flex items-center gap-3 flex-wrap">
            <button
              onClick={toggleSelectAll}
              className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-950/60 hover:bg-slate-800/80 border border-white/10 text-xs font-semibold text-slate-200 transition-colors"
            >
              {selectedPaths.size > 0 && selectedPaths.size === filteredItems.length ? (
                <CheckSquare className="w-4 h-4 text-indigo-400" />
              ) : selectedPaths.size > 0 ? (
                <CheckSquare className="w-4 h-4 text-indigo-400 opacity-70" />
              ) : (
                <Square className="w-4 h-4 text-slate-500" />
              )}
              <span>
                {selectedPaths.size > 0 ? `Selected (${selectedPaths.size})` : "Select All"}
              </span>
            </button>

            {/* Status Filter Chips */}
            <div className="flex items-center gap-1 bg-slate-950/80 p-1 rounded-xl border border-white/10 text-xs font-medium">
              {(["all", "pending", "completed", "processing", "error"] as const).map((st) => {
                const count =
                  st === "all"
                    ? scannedData?.total_files || 0
                    : st === "pending"
                    ? (scannedData?.pending_count || 0) + (scannedData?.unregistered_count || 0)
                    : st === "completed"
                    ? scannedData?.completed_count || 0
                    : st === "processing"
                    ? scannedData?.processing_count || 0
                    : scannedData?.error_count || 0;

                const isActive = statusFilter === st;
                return (
                  <button
                    key={st}
                    onClick={() => setStatusFilter(st)}
                    className={`px-2.5 py-1 rounded-lg capitalize transition-all ${
                      isActive
                        ? "bg-indigo-600 text-white font-bold shadow-xs"
                        : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    {st} <span className="text-[10px] opacity-70">({count})</span>
                  </button>
                );
              })}
            </div>

            {/* Search Input */}
            <div className="relative w-48 sm:w-60">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500" />
              <input
                type="text"
                placeholder="Search PDF or Part…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-8 pr-3 py-1.5 rounded-xl bg-slate-950 border border-white/10 text-xs text-slate-200 placeholder:text-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
          </div>

          {/* Right: Actions & View Switcher */}
          <div className="flex items-center gap-2 flex-wrap ml-auto">
            {/* Sort Dropdown */}
            <div className="flex items-center gap-1 bg-slate-950 border border-white/10 rounded-xl px-2 py-1 text-xs">
              <ArrowUpDown className="w-3.5 h-3.5 text-slate-400" />
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as any)}
                className="bg-transparent text-xs text-slate-300 outline-none cursor-pointer pr-1"
              >
                <option value="name" className="bg-slate-900">Name</option>
                <option value="size" className="bg-slate-900">File Size</option>
                <option value="pages" className="bg-slate-900">Pages</option>
                <option value="records" className="bg-slate-900">Records</option>
                <option value="status" className="bg-slate-900">Status</option>
              </select>
              <button
                onClick={() => setSortDesc(!sortDesc)}
                className="text-[10px] text-indigo-400 hover:text-indigo-300 font-bold px-1"
                title="Toggle sort direction"
              >
                {sortDesc ? "↓" : "↑"}
              </button>
            </div>

            {/* Layout Toggle */}
            <div className="flex items-center bg-slate-950 p-0.5 rounded-xl border border-white/10">
              <button
                onClick={() => setViewMode("grid")}
                className={`p-1.5 rounded-lg transition-colors ${
                  viewMode === "grid" ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-slate-200"
                }`}
                title="Grid view"
              >
                <LayoutGrid className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={() => setViewMode("table")}
                className={`p-1.5 rounded-lg transition-colors ${
                  viewMode === "table" ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-slate-200"
                }`}
                title="Table view"
              >
                <TableIcon className="w-3.5 h-3.5" />
              </button>
            </div>

            {/* Primary Batch Action Buttons */}
            {selectedPaths.size > 0 && (
              <>
                <button
                  onClick={() => void handleProcessSelected()}
                  disabled={isJobRunning || actionInProgress !== null}
                  className="px-3.5 py-1.5 rounded-xl bg-gradient-to-r from-amber-500 to-orange-600 hover:from-amber-400 hover:to-orange-500 text-white text-xs font-bold flex items-center gap-1.5 shadow-md shadow-orange-500/20 disabled:opacity-50 transition-all active:scale-95"
                >
                  <Zap className="w-3.5 h-3.5 text-yellow-200 fill-yellow-200" />
                  <span>Process Selected ({selectedPaths.size})</span>
                </button>

                <button
                  onClick={() => void handleReprocessSelected()}
                  disabled={isJobRunning || actionInProgress !== null}
                  className="px-3.5 py-1.5 rounded-xl bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white text-xs font-bold flex items-center gap-1.5 shadow-md shadow-purple-600/20 disabled:opacity-50 transition-all active:scale-95"
                  title="Re-run extraction on completed/error items"
                >
                  <RotateCcw className="w-3.5 h-3.5 text-purple-200" />
                  <span>Re-Process Selected</span>
                </button>
              </>
            )}

            <button
              onClick={() => void handleProcessAllUnprocessed()}
              disabled={isJobRunning || actionInProgress !== null || (scannedData?.pending_count === 0 && scannedData?.unregistered_count === 0)}
              className="px-4 py-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold flex items-center gap-1.5 shadow-lg shadow-indigo-600/30 disabled:opacity-40 transition-all active:scale-95"
            >
              <Play className="w-3.5 h-3.5 fill-white" />
              <span>Process All Unprocessed</span>
            </button>
          </div>
        </div>

        {/* PDF Items View: Grid or Table */}
        {isScanning ? (
          <div className="flex-1 flex flex-col items-center justify-center gap-3 text-slate-400">
            <Loader2 className="w-8 h-8 animate-spin text-indigo-400" />
            <p className="text-sm font-semibold">Scanning folder for PDF documents…</p>
          </div>
        ) : filteredItems.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center gap-3 card-vimc rounded-3xl border border-white/5 p-8 text-center">
            <Folder className="w-12 h-12 text-slate-600" />
            <div>
              <h3 className="text-sm font-bold text-slate-300">No PDF files match your filter</h3>
              <p className="text-xs text-slate-500 mt-1">
                Try selecting another folder or clearing your search filters
              </p>
            </div>
            <button
              onClick={() => {
                setSearchQuery("");
                setStatusFilter("all");
              }}
              className="px-3.5 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-200 transition-colors"
            >
              Reset Filters
            </button>
          </div>
        ) : viewMode === "grid" ? (
          /* Grid Mode */
          <div className="flex-1 overflow-y-auto min-h-0 pr-1">
            <div className="grid grid-cols-1 md:grid-cols-2 2xl:grid-cols-3 gap-3.5">
              {filteredItems.map((item) => (
                <PdfCardItem
                  key={item.stored_path}
                  item={item}
                  isSelected={selectedPaths.has(item.stored_path)}
                  onToggleSelect={() => toggleSelect(item.stored_path)}
                  onProcess={() => void handleProcessSingle(item)}
                  onReprocess={() => void handleReprocessSingle(item)}
                  isActionLoading={actionInProgress === item.stored_path}
                />
              ))}
            </div>
          </div>
        ) : (
          /* Table Mode */
          <div className="flex-1 overflow-y-auto min-h-0 rounded-2xl border border-white/5 bg-slate-900/40">
            <table className="w-full text-left text-xs border-collapse">
              <thead className="sticky top-0 bg-slate-950/90 backdrop-blur border-b border-white/10 z-10 text-[11px] text-slate-400 font-semibold uppercase tracking-wider">
                <tr>
                  <th className="p-3 w-10 text-center">
                    <input
                      type="checkbox"
                      checked={selectedPaths.size === filteredItems.length && filteredItems.length > 0}
                      onChange={toggleSelectAll}
                      className="rounded border-slate-700 text-indigo-600 focus:ring-0 cursor-pointer"
                    />
                  </th>
                  <th className="p-3">PDF Document</th>
                  <th className="p-3">Pages</th>
                  <th className="p-3">File Size</th>
                  <th className="p-3 w-48">Progress / Status</th>
                  <th className="p-3">Records</th>
                  <th className="p-3">Complete Time</th>
                  <th className="p-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5 font-medium">
                {filteredItems.map((item) => (
                  <PdfTableRowItem
                    key={item.stored_path}
                    item={item}
                    isSelected={selectedPaths.has(item.stored_path)}
                    onToggleSelect={() => toggleSelect(item.stored_path)}
                    onProcess={() => void handleProcessSingle(item)}
                    onReprocess={() => void handleReprocessSingle(item)}
                    isActionLoading={actionInProgress === item.stored_path}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

/* --------------------------------------------------------------------------
   Serena PDF Card Item Component
-------------------------------------------------------------------------- */
interface PdfItemProps {
  item: FolderPdfItem;
  isSelected: boolean;
  onToggleSelect: () => void;
  onProcess: () => void;
  onReprocess: () => void;
  isActionLoading: boolean;
}

const PdfCardItem: React.FC<PdfItemProps> = ({
  item,
  isSelected,
  onToggleSelect,
  onProcess,
  onReprocess,
  isActionLoading,
}) => {
  const { fileJobProgress, setActiveFileId, setActiveTab, deleteFile, setConfirmModal } = useOcrStore();

  const fileProgress: FileJobProgress | undefined = item.file_id ? fileJobProgress[item.file_id] : undefined;

  // Calculate live progress percentage
  const isCurrentlyProcessing = item.status === "processing" || (fileProgress && !fileProgress.done);
  const isCompleted = item.status === "completed" || (fileProgress && fileProgress.done);
  const isError = item.status === "error";
  const isPending = item.status === "pending" || item.status === "unregistered";

  const progressPct = useMemo(() => {
    if (isCompleted) return 100;
    if (fileProgress && fileProgress.pagesTotal > 0) {
      return Math.round(((fileProgress.pagesCompleted + fileProgress.pagesFailed) / fileProgress.pagesTotal) * 100);
    }
    if (item.page_count > 0 && item.pages_done > 0) {
      return Math.round((item.pages_done / item.page_count) * 100);
    }
    return 0;
  }, [isCompleted, fileProgress, item.pages_done, item.page_count]);

  const sizeMb = (item.size_bytes / (1024 * 1024)).toFixed(1);

  // Extract part tag from filename (e.g. TAM-10-WI)
  const partTag = useMemo(() => {
    const match = item.name.match(/(TAM-\d+-[A-Z0-9]+|Part-\d+|Revision\d+)/i);
    return match ? match[0] : null;
  }, [item.name]);

  const handleOpenDocView = () => {
    if (item.file_id) {
      setActiveFileId(item.file_id);
      setActiveTab("table");
    }
  };

  const handleOpenVoters = () => {
    if (item.file_id) {
      setActiveFileId(item.file_id);
      setActiveTab("voters");
    }
  };

  const handleDelete = () => {
    if (!item.file_id) return;
    setConfirmModal({
      isOpen: true,
      title: `Delete ${item.name}?`,
      message: "This will remove the file registration, OCR pages, and all extracted records from the database.",
      danger: true,
      confirmText: "Delete Document",
      onConfirm: async () => {
        await deleteFile(item.file_id!);
      },
    });
  };

  return (
    <div
      className={`group relative rounded-2xl border p-4 transition-all duration-200 flex flex-col justify-between ${
        isSelected
          ? "bg-indigo-950/30 border-indigo-500/50 shadow-md shadow-indigo-500/10"
          : "bg-slate-900/50 hover:bg-slate-900/80 border-white/5 hover:border-white/10 shadow-sm"
      }`}
    >
      {/* Top Header Row */}
      <div>
        <div className="flex items-start gap-2.5 justify-between">
          <div className="flex items-start gap-2.5 min-w-0 flex-1">
            <button
              onClick={onToggleSelect}
              className="mt-0.5 text-slate-400 hover:text-indigo-400 transition-colors shrink-0"
            >
              {isSelected ? (
                <CheckSquare className="w-4 h-4 text-indigo-400" />
              ) : (
                <Square className="w-4 h-4 text-slate-600" />
              )}
            </button>

            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5 flex-wrap">
                {partTag && (
                  <span className="px-2 py-0.5 rounded-md text-[10px] font-mono font-bold bg-indigo-500/15 border border-indigo-500/30 text-indigo-300">
                    {partTag}
                  </span>
                )}
                {isCompleted && (
                  <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 flex items-center gap-1">
                    <CheckCircle2 className="w-3 h-3" /> Processed
                  </span>
                )}
                {isCurrentlyProcessing && (
                  <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-indigo-500/20 border border-indigo-500/40 text-indigo-300 animate-pulse flex items-center gap-1">
                    <Loader2 className="w-3 h-3 animate-spin" /> Processing
                  </span>
                )}
                {isPending && (
                  <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-amber-500/10 border border-amber-500/20 text-amber-400 flex items-center gap-1">
                    <Clock className="w-3 h-3" /> Pending
                  </span>
                )}
                {isError && (
                  <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-rose-500/10 border border-rose-500/20 text-rose-400 flex items-center gap-1">
                    <AlertTriangle className="w-3 h-3" /> Error
                  </span>
                )}
              </div>

              <h4
                className="text-xs font-semibold text-slate-200 mt-1.5 break-all leading-snug group-hover:text-white transition-colors"
                title={item.name}
              >
                {item.name}
              </h4>
            </div>
          </div>

          {/* Quick Actions Menu */}
          {item.file_id && isCompleted && (
            <div className="flex items-center gap-1 shrink-0 opacity-80 group-hover:opacity-100 transition-opacity">
              <button
                onClick={handleOpenDocView}
                className="p-1 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition-colors"
                title="View document grid"
              >
                <Eye className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={handleOpenVoters}
                className="p-1 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition-colors"
                title="View voter roll for this PDF"
              >
                <Users className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={handleDelete}
                className="p-1 rounded-lg hover:bg-rose-500/10 text-slate-400 hover:text-rose-400 transition-colors"
                title="Delete document"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          )}
        </div>

        {/* Metadata Badges: Page count, MB, Records, Time */}
        <div className="grid grid-cols-3 gap-2 mt-3 pt-2.5 border-t border-white/5 text-[11px] font-mono">
          <div className="bg-slate-950/60 p-2 rounded-xl border border-white/5 flex flex-col">
            <span className="text-[10px] text-slate-500 uppercase tracking-wider">Pages</span>
            <span className="font-bold text-slate-200 flex items-center gap-1 mt-0.5">
              <FileText className="w-3 h-3 text-indigo-400" />
              {item.page_count || 1} pgs
            </span>
          </div>

          <div className="bg-slate-950/60 p-2 rounded-xl border border-white/5 flex flex-col">
            <span className="text-[10px] text-slate-500 uppercase tracking-wider">File Size</span>
            <span className="font-bold text-slate-200 flex items-center gap-1 mt-0.5">
              <HardDrive className="w-3 h-3 text-amber-400" />
              {sizeMb} MB
            </span>
          </div>

          <div className="bg-slate-950/60 p-2 rounded-xl border border-white/5 flex flex-col">
            <span className="text-[10px] text-slate-500 uppercase tracking-wider">Duration</span>
            <span className="font-bold text-slate-200 flex items-center gap-1 mt-0.5">
              <Clock className="w-3 h-3 text-purple-400" />
              {item.ocr_duration_sec ? `${item.ocr_duration_sec}s` : "—"}
            </span>
          </div>
        </div>

        {/* Extracted records tally (if completed) */}
        {isCompleted && item.records_count > 0 && (
          <div className="mt-2.5 px-2.5 py-1.5 rounded-xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-between text-xs">
            <span className="text-[11px] text-purple-300 font-medium flex items-center gap-1.5">
              <Users className="w-3.5 h-3.5 text-purple-400" />
              Extracted Records
            </span>
            <span className="font-bold text-purple-200 font-mono">
              {item.records_count} voters
            </span>
          </div>
        )}

        {/* Progress Bar & Percentage */}
        <div className="mt-3 space-y-1">
          <div className="flex items-center justify-between text-[10px] font-mono">
            <span className="text-slate-400">
              {isCurrentlyProcessing
                ? `Extracting (${fileProgress?.pagesCompleted ?? item.pages_done}/${fileProgress?.pagesTotal ?? item.page_count} pgs)`
                : isCompleted
                ? "100% Extracted"
                : "Not started"}
            </span>
            <span className={`font-bold ${isCompleted ? "text-emerald-400" : isCurrentlyProcessing ? "text-indigo-400" : "text-slate-500"}`}>
              {progressPct}%
            </span>
          </div>

          <div className="w-full h-2 rounded-full bg-slate-950 border border-white/5 overflow-hidden p-0.5">
            <div
              className={`h-full rounded-full transition-all duration-300 ${
                isCompleted
                  ? "bg-gradient-to-r from-emerald-500 to-teal-400"
                  : isCurrentlyProcessing
                  ? "bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 animate-pulse"
                  : "bg-slate-800"
              }`}
              style={{ width: `${progressPct}%` }}
            />
          </div>
        </div>
      </div>

      {/* Action Button: Process vs Re-Process */}
      <div className="mt-4 pt-3 border-t border-white/5 flex items-center gap-2">
        {isCompleted ? (
          <button
            onClick={onReprocess}
            disabled={isActionLoading}
            className="flex-1 py-2 px-3 rounded-xl bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white text-xs font-bold flex items-center justify-center gap-1.5 shadow-md shadow-purple-600/20 transition-all active:scale-95 disabled:opacity-50"
          >
            {isActionLoading ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <RotateCcw className="w-3.5 h-3.5" />
            )}
            <span>Re-Process</span>
          </button>
        ) : isError ? (
          <button
            onClick={onReprocess}
            disabled={isActionLoading}
            className="flex-1 py-2 px-3 rounded-xl bg-gradient-to-r from-rose-600 to-amber-600 hover:from-rose-500 hover:to-amber-500 text-white text-xs font-bold flex items-center justify-center gap-1.5 shadow-md shadow-rose-600/20 transition-all active:scale-95 disabled:opacity-50"
          >
            {isActionLoading ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <RotateCcw className="w-3.5 h-3.5" />
            )}
            <span>Retry Re-Process</span>
          </button>
        ) : isCurrentlyProcessing ? (
          <div className="flex-1 py-2 px-3 rounded-xl bg-indigo-600/20 border border-indigo-500/40 text-indigo-300 text-xs font-bold flex items-center justify-center gap-2">
            <Loader2 className="w-3.5 h-3.5 animate-spin text-indigo-400" />
            <span>Processing OCR…</span>
          </div>
        ) : (
          <button
            onClick={onProcess}
            disabled={isActionLoading}
            className="flex-1 py-2 px-3 rounded-xl bg-gradient-to-r from-amber-500 to-orange-600 hover:from-amber-400 hover:to-orange-500 text-white text-xs font-bold flex items-center justify-center gap-1.5 shadow-md shadow-orange-500/20 transition-all active:scale-95 disabled:opacity-50"
          >
            {isActionLoading ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Play className="w-3.5 h-3.5 fill-white" />
            )}
            <span>Process</span>
          </button>
        )}
      </div>
    </div>
  );
};

/* --------------------------------------------------------------------------
   Serena PDF Table Row Item Component
-------------------------------------------------------------------------- */
const PdfTableRowItem: React.FC<PdfItemProps> = ({
  item,
  isSelected,
  onToggleSelect,
  onProcess,
  onReprocess,
  isActionLoading,
}) => {
  const { fileJobProgress } = useOcrStore();
  const fileProgress: FileJobProgress | undefined = item.file_id ? fileJobProgress[item.file_id] : undefined;

  const isCurrentlyProcessing = item.status === "processing" || (fileProgress && !fileProgress.done);
  const isCompleted = item.status === "completed" || (fileProgress && fileProgress.done);
  const isError = item.status === "error";
  const isPending = item.status === "pending" || item.status === "unregistered";

  const progressPct = useMemo(() => {
    if (isCompleted) return 100;
    if (fileProgress && fileProgress.pagesTotal > 0) {
      return Math.round(((fileProgress.pagesCompleted + fileProgress.pagesFailed) / fileProgress.pagesTotal) * 100);
    }
    if (item.page_count > 0 && item.pages_done > 0) {
      return Math.round((item.pages_done / item.page_count) * 100);
    }
    return 0;
  }, [isCompleted, fileProgress, item.pages_done, item.page_count]);

  const sizeMb = (item.size_bytes / (1024 * 1024)).toFixed(1);

  return (
    <tr
      className={`hover:bg-slate-900/80 transition-colors ${
        isSelected ? "bg-indigo-950/30" : ""
      }`}
    >
      <td className="p-3 text-center">
        <input
          type="checkbox"
          checked={isSelected}
          onChange={onToggleSelect}
          className="rounded border-slate-700 text-indigo-600 focus:ring-0 cursor-pointer"
        />
      </td>
      <td className="p-3">
        <div className="flex items-center gap-2">
          <FileText className={`w-4 h-4 shrink-0 ${isCompleted ? "text-emerald-400" : isCurrentlyProcessing ? "text-indigo-400" : "text-slate-400"}`} />
          <span className="font-semibold text-slate-200 break-all">{item.name}</span>
        </div>
      </td>
      <td className="p-3 font-mono text-slate-300 whitespace-nowrap">
        {item.page_count || 1} pgs
      </td>
      <td className="p-3 font-mono text-slate-300 whitespace-nowrap">
        {sizeMb} MB
      </td>
      <td className="p-3">
        <div className="space-y-1 w-44">
          <div className="flex items-center justify-between text-[10px] font-mono">
            <span className="capitalize text-slate-400">{item.status}</span>
            <span className="font-bold text-slate-300">{progressPct}%</span>
          </div>
          <div className="w-full h-1.5 rounded-full bg-slate-950 overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-300 ${
                isCompleted
                  ? "bg-emerald-500"
                  : isCurrentlyProcessing
                  ? "bg-indigo-500 animate-pulse"
                  : "bg-slate-800"
              }`}
              style={{ width: `${progressPct}%` }}
            />
          </div>
        </div>
      </td>
      <td className="p-3 font-mono text-purple-300 font-bold whitespace-nowrap">
        {item.records_count ? `${item.records_count} voters` : "—"}
      </td>
      <td className="p-3 font-mono text-slate-400 whitespace-nowrap">
        {item.ocr_duration_sec ? `${item.ocr_duration_sec}s` : "—"}
      </td>
      <td className="p-3 text-right whitespace-nowrap">
        {isCompleted ? (
          <button
            onClick={onReprocess}
            disabled={isActionLoading}
            className="px-3 py-1.5 rounded-xl bg-purple-600/20 hover:bg-purple-600 border border-purple-500/30 text-purple-300 hover:text-white text-xs font-bold inline-flex items-center gap-1.5 transition-all"
          >
            {isActionLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <RotateCcw className="w-3 h-3" />}
            Re-Process
          </button>
        ) : isError ? (
          <button
            onClick={onReprocess}
            disabled={isActionLoading}
            className="px-3 py-1.5 rounded-xl bg-rose-600/20 hover:bg-rose-600 border border-rose-500/30 text-rose-300 hover:text-white text-xs font-bold inline-flex items-center gap-1.5 transition-all"
          >
            {isActionLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <RotateCcw className="w-3 h-3" />}
            Retry
          </button>
        ) : isCurrentlyProcessing ? (
          <span className="px-3 py-1.5 rounded-xl bg-indigo-600/20 text-indigo-300 text-xs font-bold inline-flex items-center gap-1.5">
            <Loader2 className="w-3 h-3 animate-spin" /> Extracting…
          </span>
        ) : (
          <button
            onClick={onProcess}
            disabled={isActionLoading}
            className="px-3 py-1.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 text-xs font-bold inline-flex items-center gap-1.5 transition-all"
          >
            {isActionLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3 fill-slate-950" />}
            Process
          </button>
        )}
      </td>
    </tr>
  );
};

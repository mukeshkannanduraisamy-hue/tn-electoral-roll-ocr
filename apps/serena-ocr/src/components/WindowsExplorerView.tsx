"use client";

import React, { useState, useMemo } from "react";
import {
  Folder,
  FolderOpen,
  FileText,
  Search,
  RefreshCw,
  Zap,
  RotateCcw,
  CheckSquare,
  Square,
  CheckCircle2,
  Clock,
  AlertTriangle,
  Loader2,
  HardDrive,
  LayoutGrid,
  List,
  ChevronRight,
  Database,
  Download,
  Info,
  ChevronLeft,
  ArrowUp,
  X,
  Sparkles,
} from "lucide-react";
import { useSerenaStore } from "@/store/useSerenaStore";
import { FolderPdfItem } from "@/types";
import { toast } from "sonner";

export const WindowsExplorerView: React.FC = () => {
  const {
    folderPath,
    setFolderPath,
    scanCurrentFolder,
    scannedData,
    isScanning,
    selectedItem,
    setSelectedItem,
    selectedPaths,
    toggleSelect,
    toggleSelectAll,
    searchQuery,
    setSearchQuery,
    statusFilter,
    setStatusFilter,
    fileJobProgress,
    processSingle,
    reprocessSingle,
    processSelected,
    reprocessSelected,
    processAllUnprocessed,
    actionInProgress,
    activeJobStatus,
    activeJobProgress,
    pagesPerSec,
    autoInsertToDb,
    toggleAutoInsertToDb,
    setActiveTab,
    liveExtractedElectors,
    isLoadingElectors,
  } = useSerenaStore();

  const [viewStyle, setViewStyle] = useState<"details" | "tiles" | "icons">("details");
  const [showDetailsPane, setShowDetailsPane] = useState(true);
  const [isEditingPath, setIsEditingPath] = useState(false);
  const [pathInput, setPathInput] = useState(folderPath);

  const isJobRunning = activeJobStatus === "running";

  // Filter items
  const filteredItems = useMemo(() => {
    if (!scannedData?.items) return [];
    return scannedData.items.filter((item) => {
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        if (!item.name.toLowerCase().includes(q) && !item.folder_name.toLowerCase().includes(q)) {
          return false;
        }
      }
      if (statusFilter === "all") return true;
      if (statusFilter === "pending") return item.status === "pending" || item.status === "unregistered";
      if (statusFilter === "completed") return item.status === "completed";
      if (statusFilter === "processing") return item.status === "processing";
      if (statusFilter === "error") return item.status === "error";
      return true;
    });
  }, [scannedData, searchQuery, statusFilter]);

  // Statistics
  const stats = useMemo(() => {
    const total = scannedData?.items?.length || 0;
    const completed = scannedData?.items?.filter((i) => i.status === "completed").length || 0;
    const pending = total - completed;
    return { total, completed, pending };
  }, [scannedData]);

  const handleFolderSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (pathInput.trim()) {
      setFolderPath(pathInput.trim());
      void scanCurrentFolder(pathInput.trim());
      setIsEditingPath(false);
    }
  };

  const handleSelectFolderDialog = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      const firstFile = files[0];
      const relativePath = firstFile.webkitRelativePath;
      if (relativePath) {
        const folderName = relativePath.split("/")[0];
        const newPath = folderPath.includes(":")
          ? `${folderPath.substring(0, folderPath.lastIndexOf("\\") + 1)}${folderName}`
          : folderName;
        setFolderPath(newPath);
        setPathInput(newPath);
        void scanCurrentFolder(newPath);
      }
    }
  };

  return (
    <div className="flex-1 flex flex-col h-full min-h-0 bg-white dark:bg-[#191919] text-slate-800 dark:text-slate-200 select-none overflow-hidden font-sans border-t border-slate-200 dark:border-white/10">
      {/* 1. Windows Explorer Address & Search Bar */}
      <div className="px-3 py-2 bg-[#F3F3F3] dark:bg-[#202020] border-b border-slate-300 dark:border-white/10 flex items-center gap-2 shrink-0 text-xs">
        {/* Navigation Buttons */}
        <div className="flex items-center gap-1">
          <button
            onClick={() => void scanCurrentFolder()}
            className="p-1.5 rounded hover:bg-slate-200 dark:hover:bg-white/10 text-slate-600 dark:text-slate-400"
            title="Refresh (F5)"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isScanning ? "animate-spin" : ""}`} />
          </button>
          <button
            onClick={() => {
              const parentPath = folderPath.substring(0, folderPath.lastIndexOf("\\"));
              if (parentPath) {
                setFolderPath(parentPath);
                setPathInput(parentPath);
                void scanCurrentFolder(parentPath);
              }
            }}
            className="p-1.5 rounded hover:bg-slate-200 dark:hover:bg-white/10 text-slate-600 dark:text-slate-400"
            title="Up to Parent Directory"
          >
            <ArrowUp className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Address Breadcrumb / Path Input Bar */}
        <div className="flex-1 flex items-center bg-white dark:bg-[#2D2D2D] border border-slate-300 dark:border-white/15 rounded px-2.5 py-1 focus-within:ring-1 focus-within:ring-blue-500 shadow-xs">
          <Folder className="w-4 h-4 text-amber-500 mr-2 shrink-0 fill-amber-500" />

          {isEditingPath ? (
            <form onSubmit={handleFolderSubmit} className="flex-1 flex items-center">
              <input
                type="text"
                value={pathInput}
                onChange={(e) => setPathInput(e.target.value)}
                onBlur={() => setIsEditingPath(false)}
                autoFocus
                className="w-full bg-transparent text-xs font-mono text-slate-900 dark:text-slate-100 focus:outline-none"
              />
            </form>
          ) : (
            <div
              onClick={() => {
                setPathInput(folderPath);
                setIsEditingPath(true);
              }}
              className="flex-1 flex items-center gap-1 text-xs font-mono text-slate-700 dark:text-slate-300 cursor-text overflow-hidden truncate"
            >
              {folderPath.split(/[\/\\]/).map((part, idx, arr) => (
                <React.Fragment key={idx}>
                  <span className="hover:bg-slate-100 dark:hover:bg-white/10 px-1 rounded cursor-pointer truncate">
                    {part || "This PC"}
                  </span>
                  {idx < arr.length - 1 && (
                    <ChevronRight className="w-3 h-3 text-slate-400 shrink-0" />
                  )}
                </React.Fragment>
              ))}
            </div>
          )}

          {/* Browse Directory Button */}
          <label className="ml-1 px-2 py-0.5 rounded bg-slate-100 dark:bg-white/10 hover:bg-slate-200 dark:hover:bg-white/15 text-[11px] font-medium text-slate-700 dark:text-slate-300 cursor-pointer shrink-0">
            <span>Browse…</span>
            <input
              type="file"
              // @ts-ignore
              webkitdirectory="true"
              directory="true"
              multiple
              onChange={handleSelectFolderDialog}
              className="hidden"
            />
          </label>
        </div>

        {/* Search in Folder Input */}
        <div className="w-56 flex items-center bg-white dark:bg-[#2D2D2D] border border-slate-300 dark:border-white/15 rounded px-2.5 py-1 focus-within:ring-1 focus-within:ring-blue-500 shadow-xs">
          <Search className="w-3.5 h-3.5 text-slate-400 mr-2 shrink-0" />
          <input
            type="text"
            placeholder={`Search ${folderPath.split(/[\/\\]/).pop() || "Folder"}…`}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-transparent text-xs text-slate-900 dark:text-slate-100 placeholder:text-slate-400 focus:outline-none"
          />
          {searchQuery && (
            <button onClick={() => setSearchQuery("")} className="text-slate-400 hover:text-slate-600">
              <X className="w-3 h-3" />
            </button>
          )}
        </div>
      </div>

      {/* 2. Windows Explorer Ribbon / Command Bar */}
      <div className="px-3 py-1.5 bg-[#F9F9F9] dark:bg-[#252525] border-b border-slate-200 dark:border-white/10 flex items-center justify-between gap-2 shrink-0 text-xs flex-wrap">
        {/* Left Actions */}
        <div className="flex items-center gap-1.5 flex-wrap">
          <button
            onClick={() => void processAllUnprocessed()}
            disabled={isJobRunning || stats.pending === 0}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-blue-600 hover:bg-blue-700 text-white font-semibold shadow-xs disabled:opacity-50 transition-all active:scale-95"
          >
            <Zap className="w-3.5 h-3.5 fill-white" />
            <span>Process All Pending ({stats.pending})</span>
          </button>

          {selectedPaths.size > 0 && (
            <>
              <button
                onClick={() => void processSelected()}
                disabled={isJobRunning}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-amber-600 hover:bg-amber-700 text-white font-semibold shadow-xs disabled:opacity-50 transition-all active:scale-95"
              >
                <Zap className="w-3.5 h-3.5" />
                <span>Process Selected ({selectedPaths.size})</span>
              </button>

              <button
                onClick={() => void reprocessSelected()}
                disabled={isJobRunning}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-slate-200 dark:bg-white/10 hover:bg-slate-300 dark:hover:bg-white/15 text-slate-800 dark:text-slate-200 font-medium transition-all"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                <span>Re-Process</span>
              </button>
            </>
          )}

          <div className="h-4 w-[1px] bg-slate-300 dark:bg-white/15 mx-1" />

          {/* Select All */}
          <button
            onClick={toggleSelectAll}
            className="flex items-center gap-1 px-2.5 py-1.5 rounded hover:bg-slate-200 dark:hover:bg-white/10 text-slate-700 dark:text-slate-300 font-medium"
          >
            {selectedPaths.size > 0 && selectedPaths.size === filteredItems.length ? (
              <CheckSquare className="w-3.5 h-3.5 text-blue-600" />
            ) : selectedPaths.size > 0 ? (
              <CheckSquare className="w-3.5 h-3.5 text-blue-600 opacity-70" />
            ) : (
              <Square className="w-3.5 h-3.5 text-slate-400" />
            )}
            <span>Select all</span>
          </button>
        </div>

        {/* Right View Switchers & Details Pane Toggle */}
        <div className="flex items-center gap-1.5">
          <div className="flex items-center bg-slate-200/70 dark:bg-white/5 p-0.5 rounded border border-slate-300 dark:border-white/10">
            <button
              onClick={() => setViewStyle("details")}
              className={`p-1 rounded ${viewStyle === "details" ? "bg-white dark:bg-white/15 shadow-xs text-blue-600 dark:text-blue-400 font-bold" : "text-slate-500"}`}
              title="Details View (Table)"
            >
              <List className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => setViewStyle("tiles")}
              className={`p-1 rounded ${viewStyle === "tiles" ? "bg-white dark:bg-white/15 shadow-xs text-blue-600 dark:text-blue-400 font-bold" : "text-slate-500"}`}
              title="Tiles View (Cards)"
            >
              <LayoutGrid className="w-3.5 h-3.5" />
            </button>
          </div>

          <button
            onClick={() => setShowDetailsPane(!showDetailsPane)}
            className={`px-2 py-1 rounded border transition-colors flex items-center gap-1 ${
              showDetailsPane
                ? "bg-blue-50 dark:bg-blue-500/10 border-blue-300 dark:border-blue-500/30 text-blue-600 dark:text-blue-400"
                : "border-slate-300 dark:border-white/10 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-white/10"
            }`}
            title="Toggle Preview / Details Pane"
          >
            <Info className="w-3.5 h-3.5" />
            <span className="text-[11px]">Details pane</span>
          </button>
        </div>
      </div>

      {/* 3. Main Split View: Left Navigation Tree + Center File Explorer + Right Details Pane */}
      <div className="flex-1 flex min-h-0 overflow-hidden">
        {/* Left Navigation Tree */}
        <nav className="w-48 lg:w-56 bg-[#FBFBFB] dark:bg-[#1E1E1E] border-r border-slate-200 dark:border-white/10 p-2.5 flex flex-col gap-1 shrink-0 text-xs overflow-y-auto select-none">
          <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 px-2 py-1">
            Quick access
          </div>

          <button
            onClick={() => setStatusFilter("all")}
            className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded transition-colors ${
              statusFilter === "all"
                ? "bg-blue-100/70 dark:bg-blue-600/20 text-blue-700 dark:text-blue-400 font-semibold"
                : "hover:bg-slate-200/60 dark:hover:bg-white/5 text-slate-700 dark:text-slate-300"
            }`}
          >
            <div className="flex items-center gap-2 truncate">
              <Folder className="w-4 h-4 text-amber-500 fill-amber-500 shrink-0" />
              <span className="truncate">All PDF Files</span>
            </div>
            <span className="text-[10px] font-mono font-bold text-slate-400">{stats.total}</span>
          </button>

          <button
            onClick={() => setStatusFilter("completed")}
            className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded transition-colors ${
              statusFilter === "completed"
                ? "bg-emerald-100/70 dark:bg-emerald-600/20 text-emerald-700 dark:text-emerald-400 font-semibold"
                : "hover:bg-slate-200/60 dark:hover:bg-white/5 text-slate-700 dark:text-slate-300"
            }`}
          >
            <div className="flex items-center gap-2 truncate">
              <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
              <span className="truncate">Completed</span>
            </div>
            <span className="text-[10px] font-mono font-bold text-emerald-600 dark:text-emerald-400">{stats.completed}</span>
          </button>

          <button
            onClick={() => setStatusFilter("pending")}
            className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded transition-colors ${
              statusFilter === "pending"
                ? "bg-amber-100/70 dark:bg-amber-600/20 text-amber-700 dark:text-amber-400 font-semibold"
                : "hover:bg-slate-200/60 dark:hover:bg-white/5 text-slate-700 dark:text-slate-300"
            }`}
          >
            <div className="flex items-center gap-2 truncate">
              <Clock className="w-4 h-4 text-amber-500 shrink-0" />
              <span className="truncate">Pending</span>
            </div>
            <span className="text-[10px] font-mono font-bold text-amber-600 dark:text-amber-400">{stats.pending}</span>
          </button>

          <div className="h-[1px] bg-slate-200 dark:bg-white/10 my-2" />

          <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 px-2 py-1">
            This PC (Drives)
          </div>

          <div className="flex items-center gap-2 px-2.5 py-1.5 text-slate-700 dark:text-slate-300">
            <HardDrive className="w-4 h-4 text-slate-500 shrink-0" />
            <span className="truncate">Local Disk (D:)</span>
          </div>

          <div className="ml-4 pl-2 border-l border-slate-300 dark:border-white/10 space-y-1">
            <div className="flex items-center gap-2 px-2 py-1 text-slate-700 dark:text-slate-300 font-medium">
              <FolderOpen className="w-3.5 h-3.5 text-amber-500 fill-amber-500 shrink-0" />
              <span className="truncate">{folderPath.split(/[\/\\]/).pop() || "Penn PDF"}</span>
            </div>
          </div>
        </nav>

        {/* Center Main File Area */}
        <main className="flex-1 flex flex-col min-h-0 overflow-y-auto bg-white dark:bg-[#191919]">
          {isScanning ? (
            <div className="flex-1 flex flex-col items-center justify-center gap-2 text-slate-400 p-8">
              <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
              <span className="text-xs font-semibold">Reading folder contents…</span>
            </div>
          ) : filteredItems.length === 0 ? (
            <div className="flex-1 flex flex-col items-center justify-center gap-2 text-slate-400 p-8 text-center">
              <Folder className="w-12 h-12 text-slate-300 dark:text-slate-700" />
              <div className="text-xs font-bold text-slate-700 dark:text-slate-300">This folder is empty or no files match search</div>
              <p className="text-[11px] text-slate-500">Check the path or change filter options above</p>
            </div>
          ) : viewStyle === "details" ? (
            /* Details Table View */
            <div className="min-w-full inline-block align-middle">
              <table className="w-full text-left text-xs border-collapse">
                <thead className="bg-[#F8F9FA] dark:bg-[#202020] border-b border-slate-200 dark:border-white/10 text-slate-500 dark:text-slate-400 font-medium sticky top-0 z-10 select-none">
                  <tr>
                    <th className="w-10 px-3 py-2">
                      <button onClick={toggleSelectAll}>
                        {selectedPaths.size > 0 && selectedPaths.size === filteredItems.length ? (
                          <CheckSquare className="w-3.5 h-3.5 text-blue-600" />
                        ) : selectedPaths.size > 0 ? (
                          <CheckSquare className="w-3.5 h-3.5 text-blue-600 opacity-70" />
                        ) : (
                          <Square className="w-3.5 h-3.5 text-slate-400" />
                        )}
                      </button>
                    </th>
                    <th className="px-3 py-2">Name</th>
                    <th className="px-3 py-2 w-32">Status</th>
                    <th className="px-3 py-2 w-24">Size</th>
                    <th className="px-3 py-2 w-20 text-center">Pages</th>
                    <th className="px-3 py-2 w-28 text-right">Extracted Voters</th>
                    <th className="px-3 py-2 w-28 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-white/5">
                  {filteredItems.map((item) => {
                    const isSelected = selectedItem?.stored_path === item.stored_path;
                    const isChecked = selectedPaths.has(item.stored_path);
                    const fileProgress = item.file_id ? fileJobProgress[item.file_id] : undefined;
                    const isCurrentlyProcessing = item.status === "processing" || (fileProgress && !fileProgress.done);
                    const isCompleted = item.status === "completed" || (fileProgress && fileProgress.done);

                    return (
                      <tr
                        key={item.stored_path}
                        onClick={() => setSelectedItem(item)}
                        onDoubleClick={() => {
                          if (isCompleted) {
                            void reprocessSingle(item);
                          } else {
                            void processSingle(item);
                          }
                        }}
                        className={`cursor-pointer transition-colors ${
                          isSelected
                            ? "bg-blue-100/70 dark:bg-blue-600/25 text-slate-900 dark:text-white"
                            : "hover:bg-slate-100/60 dark:hover:bg-white/5 text-slate-800 dark:text-slate-200"
                        }`}
                      >
                        <td className="px-3 py-2" onClick={(e) => e.stopPropagation()}>
                          <button onClick={() => toggleSelect(item.stored_path)}>
                            {isChecked ? (
                              <CheckSquare className="w-3.5 h-3.5 text-blue-600" />
                            ) : (
                              <Square className="w-3.5 h-3.5 text-slate-400" />
                            )}
                          </button>
                        </td>

                        <td className="px-3 py-2">
                          <div className="flex items-center gap-2 min-w-0">
                            <FileText className="w-4 h-4 text-red-500 shrink-0" />
                            <span className="truncate font-medium">{item.name}</span>
                          </div>
                        </td>

                        <td className="px-3 py-2">
                          {isCurrentlyProcessing ? (
                            <span className="inline-flex items-center gap-1 font-semibold text-blue-600 dark:text-blue-400 text-[11px]">
                              <Loader2 className="w-3 h-3 animate-spin" /> Processing…
                            </span>
                          ) : isCompleted ? (
                            <span className="inline-flex items-center gap-1 font-semibold text-emerald-600 dark:text-emerald-400 text-[11px]">
                              <CheckCircle2 className="w-3 h-3" /> Completed
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-slate-500 dark:text-slate-400 text-[11px]">
                              <Clock className="w-3 h-3" /> Pending
                            </span>
                          )}
                        </td>

                        <td className="px-3 py-2 font-mono text-[11px] text-slate-500 dark:text-slate-400">
                          {(item.size_bytes / (1024 * 1024)).toFixed(1)} MB
                        </td>

                        <td className="px-3 py-2 text-center font-mono text-[11px] text-slate-600 dark:text-slate-300">
                          {item.page_count || 1}
                        </td>

                        <td className="px-3 py-2 text-right font-mono font-bold text-emerald-600 dark:text-emerald-400 text-[11px]">
                          {item.records_count ? `${item.records_count} voters` : "—"}
                        </td>

                        <td className="px-3 py-2 text-right" onClick={(e) => e.stopPropagation()}>
                          {isCompleted ? (
                            <button
                              onClick={() => void reprocessSingle(item)}
                              disabled={actionInProgress === item.stored_path}
                              className="px-2.5 py-1 rounded bg-slate-100 dark:bg-white/10 hover:bg-slate-200 dark:hover:bg-white/15 text-[11px] font-medium text-slate-700 dark:text-slate-300 transition-colors"
                            >
                              Re-process
                            </button>
                          ) : (
                            <button
                              onClick={() => void processSingle(item)}
                              disabled={isCurrentlyProcessing || actionInProgress === item.stored_path}
                              className="px-2.5 py-1 rounded bg-blue-600 hover:bg-blue-700 text-white text-[11px] font-semibold transition-colors disabled:opacity-50"
                            >
                              {isCurrentlyProcessing ? "Running…" : "Process"}
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            /* Tiles / Cards Grid View */
            <div className="p-4 grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
              {filteredItems.map((item) => {
                const isSelected = selectedItem?.stored_path === item.stored_path;
                const isChecked = selectedPaths.has(item.stored_path);
                const fileProgress = item.file_id ? fileJobProgress[item.file_id] : undefined;
                const isCurrentlyProcessing = item.status === "processing" || (fileProgress && !fileProgress.done);
                const isCompleted = item.status === "completed" || (fileProgress && fileProgress.done);

                return (
                  <div
                    key={item.stored_path}
                    onClick={() => setSelectedItem(item)}
                    className={`p-3 rounded-lg border flex flex-col justify-between gap-2 cursor-pointer transition-all ${
                      isSelected
                        ? "bg-blue-100/70 dark:bg-blue-600/25 border-blue-400 dark:border-blue-500 shadow-xs"
                        : "bg-white dark:bg-[#202020] border-slate-200 dark:border-white/10 hover:border-slate-300 dark:hover:border-white/20"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <FileText className="w-6 h-6 text-red-500 shrink-0" />
                        <div className="min-w-0 flex-1">
                          <h4 className="text-xs font-semibold text-slate-900 dark:text-white truncate">
                            {item.name}
                          </h4>
                          <span className="text-[10px] text-slate-500 dark:text-slate-400 font-mono">
                            {(item.size_bytes / (1024 * 1024)).toFixed(1)} MB · {item.page_count || 1} pgs
                          </span>
                        </div>
                      </div>

                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          toggleSelect(item.stored_path);
                        }}
                        className="text-slate-400"
                      >
                        {isChecked ? (
                          <CheckSquare className="w-4 h-4 text-blue-600" />
                        ) : (
                          <Square className="w-4 h-4 text-slate-400" />
                        )}
                      </button>
                    </div>

                    <div className="flex items-center justify-between pt-2 border-t border-slate-100 dark:border-white/5 text-[11px]">
                      {isCompleted ? (
                        <span className="text-emerald-600 dark:text-emerald-400 font-bold flex items-center gap-1">
                          <CheckCircle2 className="w-3 h-3" /> {item.records_count || 0} Voters
                        </span>
                      ) : isCurrentlyProcessing ? (
                        <span className="text-blue-600 dark:text-blue-400 font-semibold flex items-center gap-1 animate-pulse">
                          <Loader2 className="w-3 h-3 animate-spin" /> Processing
                        </span>
                      ) : (
                        <span className="text-slate-400 flex items-center gap-1">
                          <Clock className="w-3 h-3" /> Pending
                        </span>
                      )}

                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          if (isCompleted) {
                            void reprocessSingle(item);
                          } else {
                            void processSingle(item);
                          }
                        }}
                        className="px-2 py-0.5 rounded bg-slate-100 dark:bg-white/10 hover:bg-blue-600 hover:text-white text-[10px] font-semibold transition-colors"
                      >
                        {isCompleted ? "Re-run" : "Run"}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </main>

        {/* Right Details / Preview Pane (Collapsible) */}
        {showDetailsPane && (
          <aside className="w-72 lg:w-80 bg-[#FBFBFB] dark:bg-[#1E1E1E] border-l border-slate-200 dark:border-white/10 p-4 flex flex-col gap-4 shrink-0 text-xs overflow-y-auto">
            <div className="flex items-center justify-between border-b border-slate-200 dark:border-white/10 pb-2">
              <span className="font-bold text-slate-700 dark:text-slate-300">File Details</span>
              <button
                onClick={() => setShowDetailsPane(false)}
                className="text-slate-400 hover:text-slate-600"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>

            {selectedItem ? (
              <div className="space-y-4">
                {/* File Icon & Name */}
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-red-500/10 border border-red-500/20 flex items-center justify-center">
                    <FileText className="w-6 h-6 text-red-500" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <h3 className="font-bold text-slate-900 dark:text-white truncate">
                      {selectedItem.name}
                    </h3>
                    <p className="text-[11px] text-slate-400 font-mono">
                      PDF Document ({selectedItem.page_count || 1} pages)
                    </p>
                  </div>
                </div>

                {/* Metadata List */}
                <div className="space-y-2 bg-white dark:bg-[#252525] p-3 rounded-lg border border-slate-200 dark:border-white/10 font-mono text-[11px]">
                  <div className="flex justify-between">
                    <span className="text-slate-400">File Size:</span>
                    <span className="text-slate-700 dark:text-slate-300">
                      {(selectedItem.size_bytes / (1024 * 1024)).toFixed(2)} MB
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Status:</span>
                    <span className="font-bold text-emerald-600 dark:text-emerald-400 capitalize">
                      {selectedItem.status}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Extracted Electors:</span>
                    <span className="font-bold text-blue-600 dark:text-blue-400">
                      {selectedItem.records_count || liveExtractedElectors.length || 0}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Folder:</span>
                    <span className="text-slate-700 dark:text-slate-300 truncate max-w-[140px]">
                      {selectedItem.folder_name}
                    </span>
                  </div>
                </div>

                {/* Quick Action Buttons */}
                <div className="space-y-2">
                  {selectedItem.status === "completed" ? (
                    <button
                      onClick={() => void reprocessSingle(selectedItem)}
                      disabled={actionInProgress === selectedItem.stored_path}
                      className="w-full py-2 rounded bg-slate-200 dark:bg-white/10 hover:bg-slate-300 dark:hover:bg-white/15 font-semibold text-slate-800 dark:text-slate-200 flex items-center justify-center gap-1.5 transition-colors"
                    >
                      <RotateCcw className="w-3.5 h-3.5" />
                      <span>Re-Process Document</span>
                    </button>
                  ) : (
                    <button
                      onClick={() => void processSingle(selectedItem)}
                      disabled={selectedItem.status === "processing" || actionInProgress === selectedItem.stored_path}
                      className="w-full py-2 rounded bg-blue-600 hover:bg-blue-700 font-semibold text-white flex items-center justify-center gap-1.5 transition-colors shadow-xs"
                    >
                      <Zap className="w-3.5 h-3.5 fill-white" />
                      <span>Process This Document</span>
                    </button>
                  )}

                  <button
                    onClick={() => setActiveTab("database")}
                    className="w-full py-2 rounded border border-slate-300 dark:border-white/10 hover:bg-slate-100 dark:hover:bg-white/5 font-semibold text-slate-700 dark:text-slate-300 flex items-center justify-center gap-1.5 transition-colors"
                  >
                    <Database className="w-3.5 h-3.5 text-slate-500" />
                    <span>View in Database Explorer</span>
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-48 text-center text-slate-400">
                <Info className="w-8 h-8 opacity-40 mb-2" />
                <span>Select a file to view details</span>
              </div>
            )}
          </aside>
        )}
      </div>

      {/* 4. Windows Status Bar (Bottom) */}
      <div className="px-3 py-1 bg-[#F3F3F3] dark:bg-[#202020] border-t border-slate-300 dark:border-white/10 flex items-center justify-between text-[11px] text-slate-600 dark:text-slate-400 shrink-0 font-mono">
        <div className="flex items-center gap-4">
          <span>{filteredItems.length} items</span>
          {selectedPaths.size > 0 && (
            <span className="text-blue-600 dark:text-blue-400 font-semibold">
              {selectedPaths.size} item(s) selected
            </span>
          )}
        </div>

        <div className="flex items-center gap-4">
          {isJobRunning && (
            <span className="flex items-center gap-1.5 text-blue-600 dark:text-blue-400 font-bold">
              <Loader2 className="w-3 h-3 animate-spin" />
              <span>Running: {activeJobProgress.toFixed(0)}% ({pagesPerSec.toFixed(1)} pgs/sec)</span>
            </span>
          )}

          <button
            onClick={toggleAutoInsertToDb}
            className={`hover:underline ${autoInsertToDb ? "text-emerald-600 dark:text-emerald-400 font-bold" : "text-slate-400"}`}
            title="Toggle Automatic SQLite Database Promotion"
          >
            Auto-DB: {autoInsertToDb ? "ON" : "OFF"}
          </button>

          <span>PaddleOCR PP-OCRv5 (GPU:0)</span>
        </div>
      </div>
    </div>
  );
};

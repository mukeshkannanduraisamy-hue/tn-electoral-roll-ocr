"use client";

import React, { useState } from "react";
import {
  FileText,
  Upload,
  Play,
  Download,
  AlertTriangle,
  RefreshCw,
  CheckCircle2,
  XCircle,
  Layers,
  Sun,
  Moon,
  Keyboard,
  Table as TableIcon,
  Eye,
  CheckSquare,
} from "lucide-react";
import { useOcrStore } from "@/store/useOcrStore";

interface NavbarProps {
  onOpenUpload: () => void;
  onOpenExport: () => void;
  onOpenBulkExtract: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  onOpenUpload,
  onOpenExport,
  onOpenBulkExtract,
}) => {
  const {
    theme,
    toggleTheme,
    files,
    activeFileId,
    setActiveFileId,
    activeTab,
    setActiveTab,
    recordStats,
    searchQuery,
    setSearchQuery,
    onlyIssuesFilter,
    setOnlyIssuesFilter,
    activeJobStatus,
    activeJobProgress,
    startBulkJob,
    setIsShortcutsOpen,
  } = useOcrStore();

  const [isSubmitting, setIsSubmitting] = useState(false);

  const pendingCount = files.filter((f) => f.status === "pending").length;

  const handleRunCurrent = async () => {
    if (!activeFileId || isSubmitting) return;
    try {
      setIsSubmitting(true);
      await startBulkJob([activeFileId]);
    } finally {
      setIsSubmitting(false);
    }
  };

  const isRunning = activeJobStatus === "running";

  return (
    <header className="h-16 border-b border-slate-200 dark:border-slate-800/80 bg-white/80 dark:bg-slate-950/80 backdrop-blur-md px-4 flex items-center justify-between gap-4 sticky top-0 z-30 shadow-sm transition-colors duration-200">
      {/* Brand & File Switcher */}
      <div className="flex items-center gap-4 shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-indigo-600 via-indigo-500 to-violet-500 flex items-center justify-center shadow-md shadow-indigo-500/20">
            <FileText className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-sm font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
              OCR Workspace
              <span className="text-[10px] uppercase font-extrabold tracking-wider px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-300 border border-indigo-500/20">
                TN Electoral Roll
              </span>
            </h1>
            <p className="text-[11px] text-slate-500 dark:text-slate-400">
              PaddleOCR v5 · 3x10 Grid Centroid Engine
            </p>
          </div>
        </div>

        <div className="h-6 w-px bg-slate-200 dark:bg-slate-800 hidden md:block" />

        {/* File Select Dropdown */}
        {files.length > 0 && (
          <select
            value={activeFileId || ""}
            onChange={(e) => setActiveFileId(e.target.value || null)}
            className="bg-slate-100 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-800 dark:text-slate-200 text-xs rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-indigo-500 transition-colors max-w-[200px] truncate"
          >
            {files.map((f) => (
              <option key={f.id} value={f.id}>
                {f.name} ({f.page_count}p)
              </option>
            ))}
          </select>
        )}
      </div>

      {/* Center View Tabs Switcher */}
      <div className="flex items-center gap-1 bg-slate-100 dark:bg-slate-900/90 p-1 rounded-xl border border-slate-200 dark:border-slate-800">
        <button
          onClick={() => setActiveTab("table")}
          className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all ${
            activeTab === "table"
              ? "bg-white dark:bg-slate-800 text-indigo-600 dark:text-indigo-400 shadow-sm"
              : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200"
          }`}
        >
          <TableIcon className="w-3.5 h-3.5" />
          <span>Table View</span>
        </button>

        <button
          onClick={() => setActiveTab("page")}
          className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all ${
            activeTab === "page"
              ? "bg-white dark:bg-slate-800 text-indigo-600 dark:text-indigo-400 shadow-sm"
              : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200"
          }`}
        >
          <Eye className="w-3.5 h-3.5" />
          <span>Page Image</span>
        </button>

        <button
          onClick={() => setActiveTab("review")}
          className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all ${
            activeTab === "review"
              ? "bg-white dark:bg-slate-800 text-indigo-600 dark:text-indigo-400 shadow-sm"
              : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200"
          }`}
        >
          <CheckSquare className="w-3.5 h-3.5" />
          <span>Review Queue</span>
          {recordStats && recordStats.with_errors > 0 && (
            <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-rose-500 text-white font-bold">
              {recordStats.with_errors}
            </span>
          )}
        </button>
      </div>

      {/* Right: Stats & Main Action Buttons */}
      <div className="flex items-center gap-2 shrink-0">
        {/* Search */}
        <div className="hidden xl:flex items-center relative w-48">
          <input
            type="text"
            placeholder="Search record text... (/)"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-slate-100 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-xs rounded-lg px-3 py-1.5 text-slate-800 dark:text-slate-200 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>

        {/* Job Progress Indicator */}
        {isRunning && (
          <div className="flex items-center gap-2 bg-indigo-50 dark:bg-indigo-950/60 border border-indigo-200 dark:border-indigo-500/30 rounded-lg px-3 py-1.5">
            <RefreshCw className="w-3.5 h-3.5 text-indigo-600 dark:text-indigo-400 animate-spin" />
            <div className="w-20 h-1.5 rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden">
              <div
                className="h-full bg-indigo-600 dark:bg-indigo-500 transition-all duration-300"
                style={{ width: `${activeJobProgress}%` }}
              />
            </div>
            <span className="text-xs text-indigo-700 dark:text-indigo-300 font-bold tabular-nums">
              {activeJobProgress.toFixed(0)}%
            </span>
          </div>
        )}

        {/* Upload PDF */}
        <button
          onClick={onOpenUpload}
          className="px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 dark:bg-slate-900 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-200 text-xs font-semibold flex items-center gap-1.5 transition-all border border-slate-200 dark:border-slate-800"
        >
          <Upload className="w-3.5 h-3.5 text-indigo-600 dark:text-indigo-400" />
          <span>Upload</span>
        </button>

        {/* Extract All (Bulk) */}
        {pendingCount > 0 && (
          <button
            onClick={onOpenBulkExtract}
            disabled={isRunning}
            className="px-3 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-500 text-white text-xs font-bold flex items-center gap-1.5 shadow-sm transition-all"
          >
            <Layers className="w-3.5 h-3.5" />
            <span>Extract All ({pendingCount})</span>
          </button>
        )}

        {/* Run OCR */}
        <button
          onClick={handleRunCurrent}
          disabled={isRunning || isSubmitting || !activeFileId}
          className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs font-bold flex items-center gap-1.5 shadow-sm shadow-indigo-600/30 transition-all"
        >
          {isRunning ? (
            <RefreshCw className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <Play className="w-3.5 h-3.5 fill-current" />
          )}
          <span>{isRunning ? "Running…" : "Run OCR"}</span>
        </button>

        {/* Export */}
        <button
          onClick={onOpenExport}
          className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold flex items-center gap-1.5 shadow-sm shadow-emerald-600/30 transition-all"
        >
          <Download className="w-3.5 h-3.5" />
          <span>Export</span>
        </button>

        {/* Keyboard Shortcuts Trigger */}
        <button
          onClick={() => setIsShortcutsOpen(true)}
          className="p-2 rounded-lg bg-slate-100 hover:bg-slate-200 dark:bg-slate-900 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300 transition-colors border border-slate-200 dark:border-slate-800"
          title="Keyboard Shortcuts (?)"
        >
          <Keyboard className="w-4 h-4" />
        </button>

        {/* Light/Dark Theme Switcher */}
        <button
          onClick={toggleTheme}
          className="p-2 rounded-lg bg-slate-100 hover:bg-slate-200 dark:bg-slate-900 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300 transition-colors border border-slate-200 dark:border-slate-800"
          title={`Switch to ${theme === "dark" ? "Light" : "Dark"} Mode`}
        >
          {theme === "dark" ? <Sun className="w-4 h-4 text-amber-400" /> : <Moon className="w-4 h-4 text-indigo-600" />}
        </button>
      </div>
    </header>
  );
};

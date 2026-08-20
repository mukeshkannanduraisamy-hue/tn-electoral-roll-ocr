"use client";

import React from "react";
import {
  CheckSquare,
  Square,
  Search,
  ArrowUpDown,
  LayoutGrid,
  Table as TableIcon,
  Play,
  RotateCcw,
  Zap,
} from "lucide-react";
import { useSerenaStore } from "@/store/useSerenaStore";

interface ToolbarProps {
  totalFiltered: number;
}

export const SerenaToolbar: React.FC<ToolbarProps> = ({ totalFiltered }) => {
  const {
    scannedData,
    selectedPaths,
    toggleSelectAll,
    searchQuery,
    setSearchQuery,
    statusFilter,
    setStatusFilter,
    sortBy,
    setSortBy,
    sortDesc,
    setSortDesc,
    viewMode,
    setViewMode,
    processSelected,
    reprocessSelected,
    processAllUnprocessed,
    actionInProgress,
    activeJobStatus,
  } = useSerenaStore();

  const isJobRunning = activeJobStatus === "running";
  const hasSelection = selectedPaths.size > 0;

  return (
    <div className="p-3 bg-white/80 dark:bg-obsidian-900/60 rounded-2xl border border-slate-200 dark:border-white/5 flex items-center justify-between gap-3 flex-wrap shrink-0 shadow-xs">
      {/* Left: Multi-select, Status Filter Chips, and Search */}
      <div className="flex items-center gap-3 flex-wrap">
        <button
          onClick={toggleSelectAll}
          className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-100 dark:bg-obsidian-950 hover:bg-slate-200 dark:hover:bg-obsidian-850 border border-slate-200 dark:border-white/10 text-xs font-semibold text-slate-800 dark:text-slate-200 transition-colors"
        >
          {hasSelection && selectedPaths.size === totalFiltered ? (
            <CheckSquare className="w-4 h-4 text-serena-indigo" />
          ) : hasSelection ? (
            <CheckSquare className="w-4 h-4 text-serena-indigo opacity-70" />
          ) : (
            <Square className="w-4 h-4 text-slate-400 dark:text-slate-600" />
          )}
          <span>{hasSelection ? `Selected (${selectedPaths.size})` : "Select All"}</span>
        </button>

        {/* Status Chips */}
        <div className="flex items-center gap-1 bg-slate-100 dark:bg-obsidian-950 p-1 rounded-xl border border-slate-200 dark:border-white/10 text-xs font-medium">
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
                    ? "bg-gradient-to-r from-serena-indigo to-serena-violet text-white font-bold shadow-xs"
                    : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200"
                }`}
              >
                {st} <span className="text-[10px] opacity-70">({count})</span>
              </button>
            );
          })}
        </div>

        {/* Search */}
        <div className="relative w-44 sm:w-56">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
          <input
            type="text"
            placeholder="Search PDF or Part…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 rounded-xl bg-slate-50 dark:bg-obsidian-950 border border-slate-200 dark:border-white/10 text-xs text-slate-900 dark:text-slate-200 placeholder:text-slate-400 dark:placeholder:text-slate-500 focus:outline-none focus:ring-1 focus:ring-serena-indigo"
          />
        </div>
      </div>

      {/* Right: Sort, Layout, and Batch Action Triggers */}
      <div className="flex items-center gap-2 flex-wrap ml-auto">
        {/* Sort */}
        <div className="flex items-center gap-1 bg-slate-100 dark:bg-obsidian-950 border border-slate-200 dark:border-white/10 rounded-xl px-2 py-1 text-xs">
          <ArrowUpDown className="w-3.5 h-3.5 text-slate-400" />
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as any)}
            className="bg-transparent text-xs text-slate-700 dark:text-slate-300 outline-none cursor-pointer pr-1"
          >
            <option value="name" className="bg-white dark:bg-obsidian-900">Name</option>
            <option value="size" className="bg-white dark:bg-obsidian-900">File Size</option>
            <option value="pages" className="bg-white dark:bg-obsidian-900">Pages</option>
            <option value="records" className="bg-white dark:bg-obsidian-900">Records</option>
            <option value="status" className="bg-white dark:bg-obsidian-900">Status</option>
          </select>
          <button
            onClick={() => setSortDesc(!sortDesc)}
            className="text-[10px] text-serena-indigo hover:text-indigo-600 dark:hover:text-indigo-300 font-bold px-1"
            title="Toggle sort direction"
          >
            {sortDesc ? "↓" : "↑"}
          </button>
        </div>

        {/* View Mode */}
        <div className="flex items-center bg-slate-100 dark:bg-obsidian-950 p-0.5 rounded-xl border border-slate-200 dark:border-white/10">
          <button
            onClick={() => setViewMode("grid")}
            className={`p-1.5 rounded-lg transition-colors ${
              viewMode === "grid"
                ? "bg-serena-indigo text-white shadow-xs"
                : "text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200"
            }`}
            title="Grid view"
          >
            <LayoutGrid className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => setViewMode("table")}
            className={`p-1.5 rounded-lg transition-colors ${
              viewMode === "table"
                ? "bg-serena-indigo text-white shadow-xs"
                : "text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200"
            }`}
            title="Table view"
          >
            <TableIcon className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Batch Action Buttons */}
        {hasSelection && (
          <>
            <button
              onClick={() => void processSelected()}
              disabled={isJobRunning || actionInProgress !== null}
              className="px-3.5 py-1.5 rounded-xl bg-gradient-to-r from-serena-amber to-orange-600 hover:from-amber-400 hover:to-orange-500 text-white text-xs font-bold flex items-center gap-1.5 shadow-md shadow-serena-amber/20 disabled:opacity-50 transition-all active:scale-95"
            >
              <Zap className="w-3.5 h-3.5 text-yellow-100 fill-yellow-100" />
              <span>Process Selected ({selectedPaths.size})</span>
            </button>

            <button
              onClick={() => void reprocessSelected()}
              disabled={isJobRunning || actionInProgress !== null}
              className="px-3.5 py-1.5 rounded-xl bg-gradient-to-r from-serena-violet to-serena-indigo hover:from-violet-500 hover:to-indigo-500 text-white text-xs font-bold flex items-center gap-1.5 shadow-md shadow-serena-violet/20 disabled:opacity-50 transition-all active:scale-95"
            >
              <RotateCcw className="w-3.5 h-3.5 text-purple-100" />
              <span>Re-Process Selected</span>
            </button>
          </>
        )}

        <button
          onClick={() => void processAllUnprocessed()}
          disabled={
            isJobRunning ||
            actionInProgress !== null ||
            (scannedData?.pending_count === 0 && scannedData?.unregistered_count === 0)
          }
          className="px-4 py-1.5 rounded-xl bg-gradient-to-r from-serena-indigo to-serena-violet hover:from-indigo-500 hover:to-violet-500 text-white text-xs font-bold flex items-center gap-1.5 shadow-lg shadow-serena-indigo/30 disabled:opacity-40 transition-all active:scale-95"
        >
          <Play className="w-3.5 h-3.5 fill-white" />
          <span>Process All Unprocessed</span>
        </button>
      </div>
    </div>
  );
};

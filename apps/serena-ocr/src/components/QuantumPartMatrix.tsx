"use client";

import React, { useMemo } from "react";
import {
  Folder,
  Layers,
  CheckCircle2,
  Clock,
  AlertTriangle,
  Loader2,
  CheckSquare,
  Square,
  Search,
  Zap,
  Play,
  RotateCcw,
  Sparkles,
  FileText,
} from "lucide-react";
import { useSerenaStore } from "@/store/useSerenaStore";
import { FolderPdfItem } from "@/types";

export const QuantumPartMatrix: React.FC = () => {
  const {
    scannedData,
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
    processSelected,
    reprocessSelected,
    actionInProgress,
    activeJobStatus,
  } = useSerenaStore();

  const isJobRunning = activeJobStatus === "running";

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

  const hasSelection = selectedPaths.size > 0;

  return (
    <aside className="w-80 lg:w-96 serena-glass rounded-3xl border border-slate-200 dark:border-white/5 flex flex-col min-h-0 overflow-hidden shrink-0 shadow-xs">
      {/* Top Header & Search */}
      <div className="p-4 border-b border-slate-200 dark:border-white/5 space-y-3 bg-slate-50/50 dark:bg-obsidian-950/40">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-xl bg-serena-indigo/10 border border-serena-indigo/30 flex items-center justify-center">
              <Layers className="w-4 h-4 text-serena-indigo" />
            </div>
            <div>
              <h3 className="text-xs font-black uppercase tracking-wider text-slate-800 dark:text-slate-200">
                Part Matrix
              </h3>
              <p className="text-[10px] text-slate-400 font-mono">
                {filteredItems.length} of {scannedData?.total_files ?? 0} Documents
              </p>
            </div>
          </div>

          <button
            onClick={toggleSelectAll}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-xl bg-slate-100 dark:bg-obsidian-950 hover:bg-slate-200 dark:hover:bg-obsidian-850 border border-slate-200 dark:border-white/10 text-[11px] font-semibold text-slate-700 dark:text-slate-300 transition-colors"
          >
            {hasSelection && selectedPaths.size === filteredItems.length ? (
              <CheckSquare className="w-3.5 h-3.5 text-serena-indigo" />
            ) : hasSelection ? (
              <CheckSquare className="w-3.5 h-3.5 text-serena-indigo opacity-70" />
            ) : (
              <Square className="w-3.5 h-3.5 text-slate-400 dark:text-slate-600" />
            )}
            <span>{hasSelection ? `(${selectedPaths.size})` : "All"}</span>
          </button>
        </div>

        {/* Search */}
        <div className="relative">
          <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="Search Part # or Revision…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 bg-white dark:bg-obsidian-950 border border-slate-200 dark:border-white/10 rounded-xl text-xs text-slate-900 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 focus:outline-none focus:ring-1 focus:ring-serena-indigo shadow-inner font-mono"
          />
        </div>

        {/* Status Filter Tabs */}
        <div className="flex items-center gap-1 overflow-x-auto pb-0.5 no-scrollbar text-[11px] font-mono">
          {(["all", "pending", "completed", "processing"] as const).map((st) => {
            const isActive = statusFilter === st;
            return (
              <button
                key={st}
                onClick={() => setStatusFilter(st)}
                className={`px-2.5 py-0.5 rounded-lg capitalize transition-all whitespace-nowrap ${
                  isActive
                    ? "bg-serena-indigo text-white font-bold shadow-xs"
                    : "text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 bg-slate-100/70 dark:bg-obsidian-950/60"
                }`}
              >
                {st}
              </button>
            );
          })}
        </div>
      </div>

      {/* Part Matrix List */}
      <div className="flex-1 overflow-y-auto p-2.5 space-y-2">
        {filteredItems.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-48 text-center p-4 text-slate-400">
            <FileText className="w-8 h-8 opacity-40 mb-2" />
            <span className="text-xs font-semibold">No Parts Match Filter</span>
          </div>
        ) : (
          filteredItems.map((item) => {
            const isSelected = selectedItem?.stored_path === item.stored_path;
            const isChecked = selectedPaths.has(item.stored_path);
            const fileProgress = item.file_id ? fileJobProgress[item.file_id] : undefined;
            const isCurrentlyProcessing = item.status === "processing" || (fileProgress && !fileProgress.done);
            const isCompleted = item.status === "completed" || (fileProgress && fileProgress.done);

            // Extract Part Badge
            const match = item.name.match(/(TAM-\d+-[A-Z0-9]+|Part-\d+|Revision\d+)/i);
            const partTag = match ? match[0] : item.name.slice(0, 16);

            return (
              <div
                key={item.stored_path}
                onClick={() => setSelectedItem(item)}
                className={`p-3 rounded-2xl border transition-all cursor-pointer relative group flex flex-col gap-2 ${
                  isSelected
                    ? "bg-gradient-to-r from-indigo-500/15 to-purple-500/10 border-serena-indigo/60 shadow-md shadow-serena-indigo/10"
                    : "bg-white/60 dark:bg-obsidian-950/60 border-slate-200 dark:border-white/5 hover:border-slate-300 dark:hover:border-white/15"
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0 flex-1">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        toggleSelect(item.stored_path);
                      }}
                      className="text-slate-400 hover:text-serena-indigo shrink-0"
                    >
                      {isChecked ? (
                        <CheckSquare className="w-3.5 h-3.5 text-serena-indigo" />
                      ) : (
                        <Square className="w-3.5 h-3.5 text-slate-400 dark:text-slate-600" />
                      )}
                    </button>

                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="px-2 py-0.5 rounded-md font-mono font-bold text-[10px] bg-serena-indigo/10 dark:bg-serena-indigo/20 text-serena-indigo border border-serena-indigo/30">
                          {partTag}
                        </span>

                        {isCompleted ? (
                          <span className="text-[10px] font-mono text-emerald-600 dark:text-emerald-400 flex items-center gap-1 font-bold">
                            <CheckCircle2 className="w-3 h-3" /> Done
                          </span>
                        ) : isCurrentlyProcessing ? (
                          <span className="text-[10px] font-mono text-serena-indigo flex items-center gap-1 font-bold animate-pulse">
                            <Loader2 className="w-3 h-3 animate-spin" /> Raycasting
                          </span>
                        ) : (
                          <span className="text-[10px] font-mono text-slate-400 flex items-center gap-1">
                            <Clock className="w-3 h-3" /> Pending
                          </span>
                        )}
                      </div>

                      <h4 className="text-xs font-semibold text-slate-800 dark:text-slate-200 mt-1 truncate">
                        {item.name}
                      </h4>
                    </div>
                  </div>
                </div>

                {/* Footer Metrics */}
                <div className="flex items-center justify-between text-[10px] font-mono text-slate-500 dark:text-slate-400 pt-1 border-t border-slate-100 dark:border-white/5">
                  <span>{item.page_count || 1} Sheets · {(item.size_bytes / (1024 * 1024)).toFixed(1)} MB</span>
                  <span className="font-bold text-purple-600 dark:text-purple-300">
                    {item.records_count ? `${item.records_count} electors` : "0 voters"}
                  </span>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Selected Action Floating Bar */}
      {hasSelection && (
        <div className="p-3 border-t border-slate-200 dark:border-white/5 bg-slate-50 dark:bg-obsidian-950 flex items-center gap-2 shrink-0">
          <button
            onClick={() => void processSelected()}
            disabled={isJobRunning || actionInProgress !== null}
            className="flex-1 py-1.5 px-2.5 rounded-xl bg-gradient-to-r from-serena-amber to-orange-600 hover:from-amber-400 hover:to-orange-500 text-white text-xs font-bold flex items-center justify-center gap-1.5 shadow-md shadow-serena-amber/20 disabled:opacity-50 transition-all active:scale-95"
          >
            <Zap className="w-3.5 h-3.5 text-yellow-100 fill-yellow-100" />
            <span>Process ({selectedPaths.size})</span>
          </button>

          <button
            onClick={() => void reprocessSelected()}
            disabled={isJobRunning || actionInProgress !== null}
            className="flex-1 py-1.5 px-2.5 rounded-xl bg-gradient-to-r from-serena-violet to-serena-indigo hover:from-violet-500 hover:to-indigo-500 text-white text-xs font-bold flex items-center justify-center gap-1.5 shadow-md shadow-serena-violet/20 disabled:opacity-50 transition-all active:scale-95"
          >
            <RotateCcw className="w-3.5 h-3.5 text-purple-100" />
            <span>Re-Process</span>
          </button>
        </div>
      )}
    </aside>
  );
};

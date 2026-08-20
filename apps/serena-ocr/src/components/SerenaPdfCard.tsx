"use client";

import React, { useMemo } from "react";
import {
  FileText,
  HardDrive,
  Clock,
  CheckCircle2,
  AlertTriangle,
  Loader2,
  CheckSquare,
  Square,
  Play,
  RotateCcw,
  Users,
  Trash2,
  ExternalLink,
} from "lucide-react";
import { FolderPdfItem, FileJobProgress } from "@/types";
import { useSerenaStore } from "@/store/useSerenaStore";

interface CardProps {
  item: FolderPdfItem;
}

export const SerenaPdfCard: React.FC<CardProps> = ({ item }) => {
  const {
    selectedPaths,
    toggleSelect,
    processSingle,
    reprocessSingle,
    actionInProgress,
    fileJobProgress,
    deleteRegisteredFile,
  } = useSerenaStore();

  const isSelected = selectedPaths.has(item.stored_path);
  const fileProgress: FileJobProgress | undefined = item.file_id
    ? fileJobProgress[item.file_id]
    : undefined;

  const isCurrentlyProcessing =
    item.status === "processing" || (fileProgress && !fileProgress.done);
  const isCompleted =
    item.status === "completed" || (fileProgress && fileProgress.done);
  const isError = item.status === "error";
  const isPending = item.status === "pending" || item.status === "unregistered";
  const isLoadingAction = actionInProgress === item.stored_path;

  // Calculate live progress percentage (0 - 100%)
  const progressPct = useMemo(() => {
    if (isCompleted) return 100;
    if (fileProgress && fileProgress.pagesTotal > 0) {
      return Math.round(
        ((fileProgress.pagesCompleted + fileProgress.pagesFailed) /
          fileProgress.pagesTotal) *
          100
      );
    }
    if (item.page_count > 0 && item.pages_done > 0) {
      return Math.round((item.pages_done / item.page_count) * 100);
    }
    return 0;
  }, [isCompleted, fileProgress, item.pages_done, item.page_count]);

  const sizeMb = (item.size_bytes / (1024 * 1024)).toFixed(1);

  // Extract part tag (e.g. TAM-10-WI or Part-10)
  const partTag = useMemo(() => {
    const match = item.name.match(/(TAM-\d+-[A-Z0-9]+|Part-\d+|Revision\d+)/i);
    return match ? match[0] : null;
  }, [item.name]);

  return (
    <div
      className={`serena-glass-card rounded-2xl p-4.5 flex flex-col justify-between relative group border transition-all ${
        isSelected
          ? "border-serena-indigo/60 bg-indigo-50/50 dark:bg-obsidian-850/90 shadow-md shadow-serena-indigo/10"
          : "border-slate-200 dark:border-white/5"
      }`}
    >
      {/* Top Header */}
      <div>
        <div className="flex items-start gap-2.5 justify-between">
          <div className="flex items-start gap-2.5 min-w-0 flex-1">
            <button
              onClick={() => toggleSelect(item.stored_path)}
              className="mt-0.5 text-slate-400 hover:text-serena-indigo transition-colors shrink-0"
            >
              {isSelected ? (
                <CheckSquare className="w-4 h-4 text-serena-indigo" />
              ) : (
                <Square className="w-4 h-4 text-slate-400 dark:text-slate-600" />
              )}
            </button>

            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5 flex-wrap">
                {partTag && (
                  <span className="px-2 py-0.5 rounded-md text-[10px] font-mono font-bold bg-serena-indigo/10 dark:bg-serena-indigo/15 border border-serena-indigo/30 text-serena-indigo dark:text-indigo-300">
                    {partTag}
                  </span>
                )}

                {/* Status Badge */}
                {isCompleted && (
                  <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-emerald-500/10 border border-emerald-500/25 text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
                    <CheckCircle2 className="w-3 h-3" /> Processed
                  </span>
                )}
                {isCurrentlyProcessing && (
                  <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-serena-indigo/15 dark:bg-serena-indigo/20 border border-serena-indigo/40 text-serena-indigo animate-pulse flex items-center gap-1">
                    <Loader2 className="w-3 h-3 animate-spin" /> Processing
                  </span>
                )}
                {isPending && (
                  <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-amber-500/10 border border-amber-500/25 text-amber-600 dark:text-amber-400 flex items-center gap-1">
                    <Clock className="w-3 h-3" /> Pending
                  </span>
                )}
                {isError && (
                  <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-rose-500/10 border border-rose-500/25 text-rose-600 dark:text-rose-400 flex items-center gap-1">
                    <AlertTriangle className="w-3 h-3" /> Error
                  </span>
                )}
              </div>

              {/* Document Title */}
              <h4
                className="text-xs font-semibold text-slate-800 dark:text-slate-100 mt-2 break-all leading-snug group-hover:text-serena-indigo dark:group-hover:text-white transition-colors"
                title={item.name}
              >
                {item.name}
              </h4>
            </div>
          </div>

          {/* Quick Trash (if in db) */}
          {item.file_id && (
            <button
              onClick={() => void deleteRegisteredFile(item.file_id!)}
              className="p-1 rounded-lg text-slate-400 hover:text-rose-500 hover:bg-rose-500/10 transition-colors opacity-0 group-hover:opacity-100"
              title="Delete from database"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* PDF Details Grid: Pages, MB, Duration */}
        <div className="grid grid-cols-3 gap-2 mt-3.5 pt-3 border-t border-slate-200 dark:border-white/5 text-[11px] font-mono">
          <div className="bg-slate-100 dark:bg-obsidian-950/80 p-2 rounded-xl border border-slate-200 dark:border-white/5 flex flex-col">
            <span className="text-[10px] text-slate-500 uppercase tracking-wider">Pages</span>
            <span className="font-bold text-slate-800 dark:text-slate-200 flex items-center gap-1 mt-0.5">
              <FileText className="w-3 h-3 text-serena-indigo" />
              {item.page_count || 1} pgs
            </span>
          </div>

          <div className="bg-slate-100 dark:bg-obsidian-950/80 p-2 rounded-xl border border-slate-200 dark:border-white/5 flex flex-col">
            <span className="text-[10px] text-slate-500 uppercase tracking-wider">Size</span>
            <span className="font-bold text-slate-800 dark:text-slate-200 flex items-center gap-1 mt-0.5">
              <HardDrive className="w-3 h-3 text-serena-amber" />
              {sizeMb} MB
            </span>
          </div>

          <div className="bg-slate-100 dark:bg-obsidian-950/80 p-2 rounded-xl border border-slate-200 dark:border-white/5 flex flex-col">
            <span className="text-[10px] text-slate-500 uppercase tracking-wider">Complete Time</span>
            <span className="font-bold text-slate-800 dark:text-slate-200 flex items-center gap-1 mt-0.5">
              <Clock className="w-3 h-3 text-serena-violet" />
              {item.ocr_duration_sec ? `${item.ocr_duration_sec}s` : "—"}
            </span>
          </div>
        </div>

        {/* Extracted electors tally */}
        {isCompleted && item.records_count > 0 && (
          <div className="mt-2.5 px-3 py-1.5 rounded-xl bg-purple-50 dark:bg-serena-violet/10 border border-purple-200 dark:border-serena-violet/20 flex items-center justify-between text-xs">
            <span className="text-[11px] text-purple-700 dark:text-purple-300 font-medium flex items-center gap-1.5">
              <Users className="w-3.5 h-3.5 text-serena-violet" />
              Extracted Electors
            </span>
            <span className="font-bold text-purple-800 dark:text-purple-200 font-mono">
              {item.records_count.toLocaleString()} voters
            </span>
          </div>
        )}

        {/* Progress Bar & Percentage */}
        <div className="mt-3.5 space-y-1.5">
          <div className="flex items-center justify-between text-[10px] font-mono">
            <span className="text-slate-500 dark:text-slate-400">
              {isCurrentlyProcessing
                ? `Extracting (${fileProgress?.pagesCompleted ?? item.pages_done}/${fileProgress?.pagesTotal ?? item.page_count} pgs)`
                : isCompleted
                ? "100% Extracted & Auto-Inserted"
                : "Awaiting OCR"}
            </span>
            <span
              className={`font-bold ${
                isCompleted
                  ? "text-emerald-600 dark:text-emerald-400"
                  : isCurrentlyProcessing
                  ? "text-serena-indigo"
                  : "text-slate-400"
              }`}
            >
              {progressPct}%
            </span>
          </div>

          <div className="w-full h-2 rounded-full bg-slate-200 dark:bg-obsidian-950 border border-slate-300 dark:border-white/5 overflow-hidden p-0.5">
            <div
              className={`h-full rounded-full transition-all duration-300 ${
                isCompleted
                  ? "bg-gradient-to-r from-emerald-500 to-teal-400"
                  : isCurrentlyProcessing
                  ? "bg-gradient-to-r from-serena-indigo via-serena-violet to-serena-rose animate-pulse"
                  : "bg-slate-300 dark:bg-slate-800"
              }`}
              style={{ width: `${progressPct}%` }}
            />
          </div>
        </div>
      </div>

      {/* Action Button: Process vs. Re-Process */}
      <div className="mt-4 pt-3.5 border-t border-slate-200 dark:border-white/5 flex items-center gap-2">
        {isCompleted ? (
          <button
            onClick={() => void reprocessSingle(item)}
            disabled={isLoadingAction}
            className="flex-1 py-2 px-3.5 rounded-xl bg-gradient-to-r from-serena-violet to-serena-indigo hover:from-violet-500 hover:to-indigo-500 text-white text-xs font-bold flex items-center justify-center gap-1.5 shadow-md shadow-serena-violet/20 transition-all active:scale-95 disabled:opacity-50"
          >
            {isLoadingAction ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <RotateCcw className="w-3.5 h-3.5" />
            )}
            <span>Re-Process</span>
          </button>
        ) : isError ? (
          <button
            onClick={() => void reprocessSingle(item)}
            disabled={isLoadingAction}
            className="flex-1 py-2 px-3.5 rounded-xl bg-gradient-to-r from-rose-600 to-amber-600 hover:from-rose-500 hover:to-amber-500 text-white text-xs font-bold flex items-center justify-center gap-1.5 shadow-md shadow-rose-600/20 transition-all active:scale-95 disabled:opacity-50"
          >
            {isLoadingAction ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <RotateCcw className="w-3.5 h-3.5" />
            )}
            <span>Retry Re-Process</span>
          </button>
        ) : isCurrentlyProcessing ? (
          <div className="flex-1 py-2 px-3.5 rounded-xl bg-serena-indigo/15 border border-serena-indigo/30 text-serena-indigo text-xs font-bold flex items-center justify-center gap-2">
            <Loader2 className="w-3.5 h-3.5 animate-spin text-serena-indigo" />
            <span>Processing OCR…</span>
          </div>
        ) : (
          <button
            onClick={() => void processSingle(item)}
            disabled={isLoadingAction}
            className="flex-1 py-2 px-3.5 rounded-xl bg-gradient-to-r from-serena-amber to-orange-600 hover:from-amber-400 hover:to-orange-500 text-white text-xs font-bold flex items-center justify-center gap-1.5 shadow-md shadow-serena-amber/20 transition-all active:scale-95 disabled:opacity-50"
          >
            {isLoadingAction ? (
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

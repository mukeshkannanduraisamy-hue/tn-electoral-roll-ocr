"use client";

import React, { useMemo } from "react";
import {
  FileText,
  Play,
  RotateCcw,
  Loader2,
  CheckCircle2,
  AlertTriangle,
  Clock,
  Trash2,
} from "lucide-react";
import { FolderPdfItem, FileJobProgress } from "@/types";
import { useSerenaStore } from "@/store/useSerenaStore";

interface TableProps {
  items: FolderPdfItem[];
}

export const SerenaPdfTable: React.FC<TableProps> = ({ items }) => {
  const {
    selectedPaths,
    toggleSelect,
    toggleSelectAll,
    processSingle,
    reprocessSingle,
    actionInProgress,
    fileJobProgress,
    deleteRegisteredFile,
  } = useSerenaStore();

  return (
    <div className="flex-1 overflow-y-auto min-h-0 rounded-2xl border border-slate-200 dark:border-white/5 bg-white dark:bg-obsidian-900/40 shadow-xs">
      <table className="w-full text-left text-xs border-collapse">
        <thead className="sticky top-0 bg-slate-100 dark:bg-obsidian-950/95 backdrop-blur-xl border-b border-slate-200 dark:border-white/10 z-10 text-[11px] text-slate-500 dark:text-slate-400 font-semibold uppercase tracking-wider">
          <tr>
            <th className="p-3.5 w-10 text-center">
              <input
                type="checkbox"
                checked={selectedPaths.size === items.length && items.length > 0}
                onChange={toggleSelectAll}
                className="rounded border-slate-400 dark:border-slate-700 text-serena-indigo focus:ring-0 cursor-pointer"
              />
            </th>
            <th className="p-3.5">PDF Document</th>
            <th className="p-3.5">Pages</th>
            <th className="p-3.5">File Size</th>
            <th className="p-3.5 w-48">Progress / Status</th>
            <th className="p-3.5">Records</th>
            <th className="p-3.5">Complete Time</th>
            <th className="p-3.5 text-right">Action</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-200 dark:divide-white/5 font-medium">
          {items.map((item) => (
            <TableRowItem
              key={item.stored_path}
              item={item}
              isSelected={selectedPaths.has(item.stored_path)}
              onToggleSelect={() => toggleSelect(item.stored_path)}
              onProcess={() => void processSingle(item)}
              onReprocess={() => void reprocessSingle(item)}
              onDelete={() => item.file_id && void deleteRegisteredFile(item.file_id)}
              isLoadingAction={actionInProgress === item.stored_path}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
};

const TableRowItem: React.FC<{
  item: FolderPdfItem;
  isSelected: boolean;
  onToggleSelect: () => void;
  onProcess: () => void;
  onReprocess: () => void;
  onDelete: () => void;
  isLoadingAction: boolean;
}> = ({
  item,
  isSelected,
  onToggleSelect,
  onProcess,
  onReprocess,
  onDelete,
  isLoadingAction,
}) => {
  const { fileJobProgress } = useSerenaStore();
  const fileProgress: FileJobProgress | undefined = item.file_id
    ? fileJobProgress[item.file_id]
    : undefined;

  const isCurrentlyProcessing =
    item.status === "processing" || (fileProgress && !fileProgress.done);
  const isCompleted =
    item.status === "completed" || (fileProgress && fileProgress.done);
  const isError = item.status === "error";
  const isPending = item.status === "pending" || item.status === "unregistered";

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

  return (
    <tr
      className={`hover:bg-slate-50 dark:hover:bg-obsidian-850/80 transition-colors ${
        isSelected ? "bg-indigo-50/50 dark:bg-serena-indigo/10" : ""
      }`}
    >
      <td className="p-3.5 text-center">
        <input
          type="checkbox"
          checked={isSelected}
          onChange={onToggleSelect}
          className="rounded border-slate-400 dark:border-slate-700 text-serena-indigo focus:ring-0 cursor-pointer"
        />
      </td>
      <td className="p-3.5">
        <div className="flex items-center gap-2.5">
          <FileText
            className={`w-4 h-4 shrink-0 ${
              isCompleted
                ? "text-emerald-500 dark:text-emerald-400"
                : isCurrentlyProcessing
                ? "text-serena-indigo"
                : "text-slate-400"
            }`}
          />
          <span className="font-semibold text-slate-800 dark:text-slate-100 break-all">{item.name}</span>
        </div>
      </td>
      <td className="p-3.5 font-mono text-slate-600 dark:text-slate-300 whitespace-nowrap">
        {item.page_count || 1} pgs
      </td>
      <td className="p-3.5 font-mono text-slate-600 dark:text-slate-300 whitespace-nowrap">
        {sizeMb} MB
      </td>
      <td className="p-3.5">
        <div className="space-y-1 w-44">
          <div className="flex items-center justify-between text-[10px] font-mono">
            <span className="capitalize text-slate-500 dark:text-slate-400">{item.status}</span>
            <span className="font-bold text-slate-700 dark:text-slate-200">{progressPct}%</span>
          </div>
          <div className="w-full h-1.5 rounded-full bg-slate-200 dark:bg-obsidian-950 overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-300 ${
                isCompleted
                  ? "bg-emerald-500"
                  : isCurrentlyProcessing
                  ? "bg-serena-indigo animate-pulse"
                  : "bg-slate-300 dark:bg-slate-800"
              }`}
              style={{ width: `${progressPct}%` }}
            />
          </div>
        </div>
      </td>
      <td className="p-3.5 font-mono text-purple-700 dark:text-purple-300 font-bold whitespace-nowrap">
        {item.records_count ? `${item.records_count.toLocaleString()} voters` : "—"}
      </td>
      <td className="p-3.5 font-mono text-slate-500 dark:text-slate-400 whitespace-nowrap">
        {item.ocr_duration_sec ? `${item.ocr_duration_sec}s` : "—"}
      </td>
      <td className="p-3.5 text-right whitespace-nowrap">
        {isCompleted ? (
          <button
            onClick={onReprocess}
            disabled={isLoadingAction}
            className="px-3 py-1.5 rounded-xl bg-purple-50 dark:bg-serena-violet/20 hover:bg-serena-violet border border-purple-200 dark:border-serena-violet/30 text-purple-700 dark:text-purple-200 hover:text-white text-xs font-bold inline-flex items-center gap-1.5 transition-all shadow-xs"
          >
            {isLoadingAction ? (
              <Loader2 className="w-3 h-3 animate-spin" />
            ) : (
              <RotateCcw className="w-3 h-3" />
            )}
            Re-Process
          </button>
        ) : isError ? (
          <button
            onClick={onReprocess}
            disabled={isLoadingAction}
            className="px-3 py-1.5 rounded-xl bg-rose-50 dark:bg-rose-500/20 hover:bg-rose-600 border border-rose-200 dark:border-rose-500/30 text-rose-700 dark:text-rose-300 hover:text-white text-xs font-bold inline-flex items-center gap-1.5 transition-all"
          >
            {isLoadingAction ? (
              <Loader2 className="w-3 h-3 animate-spin" />
            ) : (
              <RotateCcw className="w-3 h-3" />
            )}
            Retry
          </button>
        ) : isCurrentlyProcessing ? (
          <span className="px-3 py-1.5 rounded-xl bg-serena-indigo/15 text-serena-indigo text-xs font-bold inline-flex items-center gap-1.5">
            <Loader2 className="w-3 h-3 animate-spin" /> Extracting…
          </span>
        ) : (
          <button
            onClick={onProcess}
            disabled={isLoadingAction}
            className="px-3.5 py-1.5 rounded-xl bg-gradient-to-r from-serena-amber to-orange-600 hover:from-amber-400 hover:to-orange-500 text-white text-xs font-bold inline-flex items-center gap-1.5 transition-all shadow-xs"
          >
            {isLoadingAction ? (
              <Loader2 className="w-3 h-3 animate-spin" />
            ) : (
              <Play className="w-3.5 h-3.5 fill-white" />
            )}
            Process
          </button>
        )}
      </td>
    </tr>
  );
};

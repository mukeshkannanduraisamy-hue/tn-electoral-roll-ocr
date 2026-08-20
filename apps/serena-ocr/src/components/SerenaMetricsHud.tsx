"use client";

import React, { useMemo } from "react";
import {
  HardDrive,
  FileText,
  CheckCircle2,
  Users,
  Activity,
  Zap,
  StopCircle,
} from "lucide-react";
import { useSerenaStore } from "@/store/useSerenaStore";

export const SerenaMetricsHud: React.FC = () => {
  const {
    scannedData,
    activeJobStatus,
    activeJobProgress,
    pagesPerSec,
    etaSeconds,
    cancelActiveJob,
  } = useSerenaStore();

  const totalMb = useMemo(() => {
    if (!scannedData?.total_size_bytes) return "0.0";
    return (scannedData.total_size_bytes / (1024 * 1024)).toFixed(1);
  }, [scannedData]);

  const totalRecords = useMemo(() => {
    if (!scannedData?.items) return 0;
    return scannedData.items.reduce((acc, i) => acc + (i.records_count || 0), 0);
  }, [scannedData]);

  const isJobActive = activeJobStatus === "running";

  if (!scannedData) return null;

  return (
    <div className="px-6 py-3.5 bg-slate-50/80 dark:bg-obsidian-950/60 border-b border-slate-200 dark:border-white/5 shrink-0 flex flex-col gap-3">
      {/* Metrics Cards Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3.5">
        {/* Card 1: Volume & Files */}
        <div className="serena-glass p-3.5 rounded-2xl flex items-center gap-3.5 border border-slate-200 dark:border-white/5">
          <div className="w-10 h-10 rounded-xl bg-serena-indigo/10 border border-serena-indigo/25 flex items-center justify-center shrink-0">
            <HardDrive className="w-5 h-5 text-serena-indigo" />
          </div>
          <div className="min-w-0">
            <div className="text-[11px] text-slate-500 dark:text-slate-400 font-medium">Folder Volume</div>
            <div className="text-sm font-bold text-slate-900 dark:text-white truncate flex items-baseline gap-1.5">
              <span>{scannedData.total_files} PDFs</span>
              <span className="text-xs text-slate-400 font-mono font-normal">({totalMb} MB)</span>
            </div>
          </div>
        </div>

        {/* Card 2: Total Pages */}
        <div className="serena-glass p-3.5 rounded-2xl flex items-center gap-3.5 border border-slate-200 dark:border-white/5">
          <div className="w-10 h-10 rounded-xl bg-serena-amber/10 border border-serena-amber/25 flex items-center justify-center shrink-0">
            <FileText className="w-5 h-5 text-serena-amber" />
          </div>
          <div className="min-w-0">
            <div className="text-[11px] text-slate-500 dark:text-slate-400 font-medium">Document Sheets</div>
            <div className="text-sm font-bold text-slate-900 dark:text-white truncate font-mono">
              {scannedData.total_pages.toLocaleString()} Pages
            </div>
          </div>
        </div>

        {/* Card 3: Completed & Pending */}
        <div className="serena-glass p-3.5 rounded-2xl flex items-center gap-3.5 border border-slate-200 dark:border-white/5">
          <div className="w-10 h-10 rounded-xl bg-serena-emerald/10 border border-serena-emerald/25 flex items-center justify-center shrink-0">
            <CheckCircle2 className="w-5 h-5 text-serena-emerald" />
          </div>
          <div className="min-w-0">
            <div className="text-[11px] text-slate-500 dark:text-slate-400 font-medium">Pipeline Status</div>
            <div className="text-sm font-bold text-emerald-600 dark:text-serena-emerald truncate flex items-baseline gap-1">
              <span>{scannedData.completed_count} Done</span>
              <span className="text-xs text-slate-400 font-normal">
                · {scannedData.pending_count + scannedData.unregistered_count} Pending
              </span>
            </div>
          </div>
        </div>

        {/* Card 4: Extracted Electors */}
        <div className="serena-glass p-3.5 rounded-2xl flex items-center gap-3.5 border border-slate-200 dark:border-white/5">
          <div className="w-10 h-10 rounded-xl bg-serena-violet/10 border border-serena-violet/25 flex items-center justify-center shrink-0">
            <Users className="w-5 h-5 text-serena-violet" />
          </div>
          <div className="min-w-0">
            <div className="text-[11px] text-slate-500 dark:text-slate-400 font-medium">Extracted Electors</div>
            <div className="text-sm font-bold text-purple-700 dark:text-purple-200 truncate font-mono">
              {totalRecords.toLocaleString()} Records
            </div>
          </div>
        </div>
      </div>

      {/* Real-time Global Pipeline Banner (shown when OCR job is executing) */}
      {isJobActive && (
        <div className="p-3 rounded-2xl bg-gradient-to-r from-serena-indigo/15 via-serena-violet/15 to-serena-rose/15 border border-serena-indigo/30 flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3 min-w-0 flex-1">
            <div className="w-7 h-7 rounded-lg bg-serena-indigo/20 flex items-center justify-center shrink-0">
              <Zap className="w-4 h-4 text-serena-indigo fill-serena-indigo animate-pulse" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center justify-between text-xs font-mono mb-1">
                <span className="font-bold text-slate-800 dark:text-slate-200 flex items-center gap-2">
                  OCR Engine Active
                  {pagesPerSec > 0 && (
                    <span className="text-serena-cyan font-semibold">
                      · {pagesPerSec.toFixed(1)} pgs/sec
                    </span>
                  )}
                  {etaSeconds > 0 && (
                    <span className="text-slate-500 dark:text-slate-400 font-normal">
                      · ETA ~{etaSeconds}s
                    </span>
                  )}
                </span>
                <span className="font-bold text-serena-indigo">{Math.round(activeJobProgress)}%</span>
              </div>
              <div className="w-full h-2 rounded-full bg-slate-200 dark:bg-obsidian-950 overflow-hidden border border-slate-300 dark:border-white/10">
                <div
                  className="h-full bg-gradient-to-r from-serena-indigo via-serena-violet to-serena-rose rounded-full transition-all duration-300"
                  style={{ width: `${activeJobProgress}%` }}
                />
              </div>
            </div>
          </div>

          <button
            onClick={() => void cancelActiveJob()}
            className="px-3 py-1.5 rounded-xl bg-rose-500/20 hover:bg-rose-500/30 border border-rose-500/40 text-rose-600 dark:text-rose-300 text-xs font-semibold flex items-center gap-1.5 transition-colors shrink-0"
          >
            <StopCircle className="w-3.5 h-3.5 text-rose-500 dark:text-rose-400" />
            <span>Cancel Job</span>
          </button>
        </div>
      )}
    </div>
  );
};

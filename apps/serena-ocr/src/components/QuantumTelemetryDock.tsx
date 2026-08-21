"use client";

import React from "react";
import {
  Activity,
  Cpu,
  Clock,
  Zap,
  CheckCircle2,
  Database,
  XCircle,
  Loader2,
  Sparkles,
} from "lucide-react";
import { useSerenaStore } from "@/store/useSerenaStore";

export const QuantumTelemetryDock: React.FC = () => {
  const {
    activeJobId,
    activeJobStatus,
    activeJobProgress,
    pagesPerSec,
    etaSeconds,
    cancelActiveJob,
    autoInsertToDb,
    toggleAutoInsertToDb,
  } = useSerenaStore();

  const isJobRunning = activeJobStatus === "running";

  const formatEta = (seconds: number) => {
    if (!seconds || seconds <= 0) return "0s";
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    if (m > 0) return `${m}m ${s}s`;
    return `${s}s`;
  };

  return (
    <div className="serena-glass rounded-2xl border border-slate-200 dark:border-white/5 p-3 flex items-center justify-between gap-4 flex-wrap text-xs font-mono shrink-0 shadow-xs">
      {/* Left: Engine Telemetry Metrics */}
      <div className="flex items-center gap-4 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-pulse" />
          <span className="font-bold text-slate-900 dark:text-white uppercase tracking-wider text-[11px]">
            Quantum Telemetry
          </span>
        </div>

        <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-xl bg-slate-100 dark:bg-obsidian-950 border border-slate-200 dark:border-white/5 text-slate-700 dark:text-slate-300">
          <Zap className="w-3.5 h-3.5 text-serena-amber" />
          <span>{pagesPerSec ? pagesPerSec.toFixed(1) : "0.0"} pgs/sec</span>
        </div>

        <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-xl bg-slate-100 dark:bg-obsidian-950 border border-slate-200 dark:border-white/5 text-slate-700 dark:text-slate-300">
          <Clock className="w-3.5 h-3.5 text-serena-violet" />
          <span>ETA: {formatEta(etaSeconds)}</span>
        </div>

        <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-xl bg-slate-100 dark:bg-obsidian-950 border border-slate-200 dark:border-white/5 text-slate-700 dark:text-slate-300">
          <Cpu className="w-3.5 h-3.5 text-serena-indigo" />
          <span>GPU:0 · 3 Workers</span>
        </div>
      </div>

      {/* Center: Live Job Progress Bar */}
      {isJobRunning && (
        <div className="flex-1 min-w-[200px] max-w-md flex items-center gap-3">
          <div className="flex-1 h-2 rounded-full bg-slate-200 dark:bg-obsidian-800 overflow-hidden relative">
            <div
              className="h-full bg-gradient-to-r from-cyan-400 via-serena-indigo to-serena-violet rounded-full transition-all duration-300 shadow-xs"
              style={{ width: `${Math.max(4, activeJobProgress)}%` }}
            />
          </div>
          <span className="text-[11px] font-bold text-serena-indigo">
            {activeJobProgress.toFixed(0)}%
          </span>
          <button
            onClick={() => void cancelActiveJob()}
            className="p-1 text-rose-500 hover:bg-rose-500/10 rounded-lg transition-colors"
            title="Cancel Active Job"
          >
            <XCircle className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Right: Auto DB Ingestion & Consensus Indicator */}
      <div className="flex items-center gap-3">
        <button
          onClick={toggleAutoInsertToDb}
          className={`flex items-center gap-1.5 px-3 py-1 rounded-xl border transition-all text-[11px] font-semibold ${
            autoInsertToDb
              ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:text-emerald-400"
              : "bg-slate-100 dark:bg-obsidian-950 border-slate-200 dark:border-white/10 text-slate-400"
          }`}
          title="Auto-insert extracted voter records into SQLite database upon extraction completion"
        >
          <Database className="w-3.5 h-3.5" />
          <span>Auto-DB {autoInsertToDb ? "ON" : "OFF"}</span>
        </button>

        <span className="px-2.5 py-1 rounded-xl bg-indigo-500/10 border border-indigo-500/25 text-serena-indigo text-[11px] font-bold flex items-center gap-1">
          <Sparkles className="w-3 h-3 text-serena-indigo" />
          <span>PP-OCRv5</span>
        </span>
      </div>
    </div>
  );
};

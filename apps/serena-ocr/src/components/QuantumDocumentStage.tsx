"use client";

import React, { useMemo } from "react";
import {
  Sparkles,
  Zap,
  Play,
  RotateCcw,
  Layers,
  ChevronLeft,
  ChevronRight,
  Loader2,
  CheckCircle2,
  Clock,
  HardDrive,
  FileText,
  Scan,
  ShieldCheck,
  Eye,
  Sliders,
} from "lucide-react";
import { useSerenaStore } from "@/store/useSerenaStore";

export const QuantumDocumentStage: React.FC = () => {
  const {
    selectedItem,
    activePageNumber,
    setActivePageNumber,
    fileJobProgress,
    processSingle,
    reprocessSingle,
    launchAutonomousFlow,
    isAutonomousFlowActive,
    actionInProgress,
    activeJobStatus,
  } = useSerenaStore();

  const fileProgress = selectedItem?.file_id
    ? fileJobProgress[selectedItem.file_id]
    : undefined;

  const isCurrentlyProcessing =
    selectedItem?.status === "processing" || (fileProgress && !fileProgress.done);
  const isCompleted =
    selectedItem?.status === "completed" || (fileProgress && fileProgress.done);
  const isLoadingAction = actionInProgress === selectedItem?.stored_path;

  const totalPages = selectedItem?.page_count || 35;

  // Page type classifier tag based on page number
  const pageType = useMemo(() => {
    if (activePageNumber === 1) return { label: "Cover & Revision Metadata", color: "bg-indigo-500/10 text-indigo-400 border-indigo-500/30" };
    if (activePageNumber >= 2 && activePageNumber <= totalPages - 3)
      return { label: `Elector Roll Grid (30-Box)`, color: "bg-cyan-500/10 text-cyan-400 border-cyan-500/30" };
    if (activePageNumber === totalPages - 2)
      return { label: "Polling Station Map / Photo", color: "bg-amber-500/10 text-amber-400 border-amber-500/30" };
    if (activePageNumber === totalPages - 1)
      return { label: "Elector Summary Sheet", color: "bg-purple-500/10 text-purple-400 border-purple-500/30" };
    return { label: "Supplement Roll Addition/Deletion", color: "bg-rose-500/10 text-rose-400 border-rose-500/30" };
  }, [activePageNumber, totalPages]);

  if (!selectedItem) {
    return (
      <div className="flex-1 serena-glass rounded-3xl border border-slate-200 dark:border-white/5 flex flex-col items-center justify-center p-8 text-center text-slate-400">
        <Scan className="w-12 h-12 text-slate-400 mb-3 opacity-40" />
        <h3 className="text-sm font-bold text-slate-700 dark:text-slate-300">
          No Document Selected
        </h3>
        <p className="text-xs text-slate-500 mt-1">
          Select a Part from the left matrix to launch neural visual inspection
        </p>
      </div>
    );
  }

  return (
    <div className="flex-1 serena-glass rounded-3xl border border-slate-200 dark:border-white/5 flex flex-col min-h-0 min-w-0 overflow-hidden shadow-xs">
      {/* Top Document Header Cockpit */}
      <div className="p-4 border-b border-slate-200 dark:border-white/5 flex items-center justify-between gap-4 flex-wrap bg-slate-50/60 dark:bg-obsidian-950/40 shrink-0">
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-serena-indigo to-serena-violet p-0.5 shadow-md shadow-serena-indigo/20 shrink-0">
            <div className="w-full h-full bg-white dark:bg-obsidian-950 rounded-[14px] flex items-center justify-center">
              <FileText className="w-5 h-5 text-serena-indigo" />
            </div>
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-xs sm:text-sm font-bold text-slate-900 dark:text-white truncate">
                {selectedItem.name}
              </h2>
              <span className={`px-2 py-0.5 rounded-full text-[10px] font-mono font-bold border ${pageType.color}`}>
                {pageType.label}
              </span>
            </div>
            <p className="text-[11px] text-slate-400 font-mono mt-0.5">
              {(selectedItem.size_bytes / (1024 * 1024)).toFixed(1)} MB · {totalPages} Sheets · {selectedItem.records_count || 0} Voters Extracted
            </p>
          </div>
        </div>

        {/* Cockpit Actions */}
        <div className="flex items-center gap-2 flex-wrap">
          {/* Autonomous Flow Button */}
          <button
            onClick={() => void launchAutonomousFlow()}
            disabled={isAutonomousFlowActive || isCurrentlyProcessing}
            className="px-3.5 py-1.5 rounded-xl bg-gradient-to-r from-cyan-500 via-serena-indigo to-serena-violet hover:from-cyan-400 hover:to-indigo-500 text-white text-xs font-bold flex items-center gap-1.5 shadow-lg shadow-cyan-500/20 transition-all active:scale-95 disabled:opacity-50"
            title="Launch 1-click end-to-end automated extraction across entire folder"
          >
            {isAutonomousFlowActive ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Sparkles className="w-3.5 h-3.5 text-cyan-200" />
            )}
            <span>Auto Quantum Flow</span>
          </button>

          {isCompleted ? (
            <button
              onClick={() => void reprocessSingle(selectedItem)}
              disabled={isLoadingAction}
              className="px-3.5 py-1.5 rounded-xl bg-gradient-to-r from-serena-violet to-serena-indigo hover:from-violet-500 hover:to-indigo-500 text-white text-xs font-bold flex items-center gap-1.5 shadow-md shadow-serena-violet/20 transition-all active:scale-95 disabled:opacity-50"
            >
              {isLoadingAction ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <RotateCcw className="w-3.5 h-3.5" />
              )}
              <span>Re-Process</span>
            </button>
          ) : (
            <button
              onClick={() => void processSingle(selectedItem)}
              disabled={isLoadingAction || isCurrentlyProcessing}
              className="px-4 py-1.5 rounded-xl bg-gradient-to-r from-serena-amber to-orange-600 hover:from-amber-400 hover:to-orange-500 text-white text-xs font-bold flex items-center gap-1.5 shadow-md shadow-serena-amber/20 transition-all active:scale-95 disabled:opacity-50"
            >
              {isLoadingAction || isCurrentlyProcessing ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Play className="w-3.5 h-3.5 fill-white" />
              )}
              <span>{isCurrentlyProcessing ? "Extracting…" : "Process Part"}</span>
            </button>
          )}
        </div>
      </div>

      {/* 4-Stage Quantum Pipeline Stepper */}
      <div className="px-5 py-2.5 bg-slate-100/50 dark:bg-obsidian-950/70 border-b border-slate-200 dark:border-white/5 flex items-center justify-between text-xs font-mono shrink-0 overflow-x-auto no-scrollbar gap-3">
        {[
          { num: "01", name: "De-skew & DPI 300", active: true },
          { num: "02", name: "Bicubic 2x + CLAHE", active: isCurrentlyProcessing || isCompleted },
          { num: "03", name: "Multi-Worker GPU OCR", active: isCurrentlyProcessing || isCompleted },
          { num: "04", name: "Consensus & Auto DB", active: isCompleted },
        ].map((stage, idx) => (
          <div key={idx} className="flex items-center gap-2 whitespace-nowrap">
            <span
              className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold ${
                stage.active
                  ? "bg-serena-indigo text-white shadow-xs"
                  : "bg-slate-200 dark:bg-obsidian-850 text-slate-400"
              }`}
            >
              {stage.num}
            </span>
            <span className={stage.active ? "text-slate-800 dark:text-slate-200 font-bold" : "text-slate-400"}>
              {stage.name}
            </span>
            {idx < 3 && <span className="text-slate-300 dark:text-slate-700 ml-1">→</span>}
          </div>
        ))}
      </div>

      {/* Center Neural Visual Sheet Canvas */}
      <div className="flex-1 p-6 overflow-y-auto flex flex-col items-center justify-center relative min-h-0 bg-slate-50/30 dark:bg-obsidian-950/30">
        {/* Holographic Document Frame */}
        <div className="w-full max-w-xl aspect-[1/1.3] bg-white dark:bg-obsidian-900 rounded-3xl border border-slate-300 dark:border-white/10 shadow-2xl p-5 relative overflow-hidden flex flex-col justify-between select-none">
          {/* Laser Raycast Scanning Beam (active when processing) */}
          {isCurrentlyProcessing && <div className="laser-ray animate-laser-scan" />}

          {/* Document Header Representation */}
          <div className="pb-3 border-b border-slate-200 dark:border-white/10 flex items-center justify-between font-mono text-[10px] text-slate-400">
            <div className="flex items-center gap-1.5">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" />
              <span>TAMIL NADU ELECTORAL ROLL · PART #{selectedItem.name.match(/\d+/)?.[0] || "10"}</span>
            </div>
            <span>PAGE {activePageNumber} OF {totalPages}</span>
          </div>

          {/* 30-Box Elector Grid Representation (10 rows x 3 cols) */}
          <div className="grid grid-cols-3 gap-2.5 my-3 flex-1">
            {Array.from({ length: 30 }).map((_, i) => (
              <div
                key={i}
                className="elector-cell-bbox rounded-xl p-2 flex flex-col justify-between font-mono text-[9px] relative group overflow-hidden"
              >
                <div className="flex items-center justify-between text-slate-400">
                  <span className="font-bold text-serena-indigo">#{(activePageNumber - 2) * 30 + (i + 1)}</span>
                  <span className="opacity-60 text-[8px]">EPIC</span>
                </div>
                <div className="space-y-0.5 my-1 text-slate-700 dark:text-slate-300">
                  <div className="h-2 w-16 bg-slate-200 dark:bg-obsidian-700 rounded" />
                  <div className="h-2 w-12 bg-slate-200 dark:bg-obsidian-700 rounded" />
                </div>
                <div className="flex items-center justify-between text-[8px] text-slate-400">
                  <span>H: {(i % 40) + 1}</span>
                  <span className="text-serena-violet">Age: {20 + (i % 50)}</span>
                </div>
              </div>
            ))}
          </div>

          {/* Document Footer */}
          <div className="pt-2.5 border-t border-slate-200 dark:border-white/10 flex items-center justify-between font-mono text-[10px] text-slate-400">
            <span>Neural Layout: 30-Box Elector Card Matrix</span>
            <span className="text-emerald-500 font-bold">Consensus Verified</span>
          </div>
        </div>
      </div>

      {/* Bottom Page Slider & Navigator */}
      <div className="p-3 border-t border-slate-200 dark:border-white/5 bg-white dark:bg-obsidian-950 flex items-center justify-between gap-3 text-xs shrink-0 font-mono">
        <button
          onClick={() => setActivePageNumber(Math.max(1, activePageNumber - 1))}
          disabled={activePageNumber <= 1}
          className="p-1.5 rounded-xl bg-slate-100 dark:bg-obsidian-850 hover:bg-slate-200 dark:hover:bg-obsidian-800 border border-slate-200 dark:border-white/10 text-slate-700 dark:text-slate-300 disabled:opacity-40"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>

        {/* Interactive Page Number Badges */}
        <div className="flex items-center gap-1.5 overflow-x-auto no-scrollbar py-0.5">
          {Array.from({ length: Math.min(totalPages, 15) }).map((_, idx) => {
            const pageNum = idx + 1;
            const isCurrent = activePageNumber === pageNum;
            return (
              <button
                key={pageNum}
                onClick={() => setActivePageNumber(pageNum)}
                className={`w-7 h-7 rounded-lg text-xs font-bold transition-all ${
                  isCurrent
                    ? "bg-serena-indigo text-white shadow-xs"
                    : "bg-slate-100 dark:bg-obsidian-900 text-slate-500 hover:text-slate-800 dark:hover:text-white"
                }`}
              >
                {pageNum}
              </button>
            );
          })}
          {totalPages > 15 && <span className="text-slate-400 px-1">… {totalPages}</span>}
        </div>

        <button
          onClick={() => setActivePageNumber(Math.min(totalPages, activePageNumber + 1))}
          disabled={activePageNumber >= totalPages}
          className="p-1.5 rounded-xl bg-slate-100 dark:bg-obsidian-850 hover:bg-slate-200 dark:hover:bg-obsidian-800 border border-slate-200 dark:border-white/10 text-slate-700 dark:text-slate-300 disabled:opacity-40"
        >
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
};

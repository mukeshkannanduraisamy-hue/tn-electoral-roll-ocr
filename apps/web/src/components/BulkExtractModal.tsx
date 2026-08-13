"use client";

import React, { useEffect, useState } from "react";
import {
  X,
  Layers,
  CheckCircle2,
  AlertTriangle,
  Loader2,
  FileText,
  Zap,
} from "lucide-react";
import { useOcrStore, FileJobProgress } from "@/store/useOcrStore";
import { SourceFile } from "@ocr/shared-types";
import { toast } from "sonner";

interface BulkExtractModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const TEMPLATES = [
  { id: "auto", label: "Auto-detect" },
  { id: "electoral_roll_ta", label: "TN Electoral Roll (Tamil)" },
  { id: "generic", label: "Generic OCR" },
];

const OCR_ENGINES = [
  { id: "paddle", label: "PaddleOCR (High Speed - Default)" },
  { id: "eagle_vlm", label: "NVIDIA Eagle VLM (Locate-Anything)" },
];

export const BulkExtractModal: React.FC<BulkExtractModalProps> = ({
  isOpen,
  onClose,
}) => {
  const {
    files,
    activeJobStatus,
    activeJobProgress,
    fileJobProgress,
    startBulkJob,
  } = useOcrStore();

  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [templateId, setTemplateId] = useState("auto");
  const [ocrEngine, setOcrEngine] = useState("paddle");
  const [isStarting, setIsStarting] = useState(false);
  const [jobStarted, setJobStarted] = useState(false);

  useEffect(() => {
    if (isOpen) {
      const auto = files
        .filter((f) => f.status === "pending" || f.status === "error")
        .map((f) => f.id);
      setSelectedIds(new Set(auto));
      setJobStarted(false);
    }
  }, [isOpen, files]);

  if (!isOpen) return null;

  const toggleFile = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    if (selectedIds.size === files.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(files.map((f) => f.id)));
    }
  };

  const handleStart = async () => {
    if (!selectedIds.size || isStarting) return;
    try {
      setIsStarting(true);
      const job = await startBulkJob(Array.from(selectedIds), templateId, false, ocrEngine);
      if (job) setJobStarted(true);
    } catch (e) {
      toast.error("Failed to start bulk OCR extraction");
    } finally {
      setIsStarting(false);
    }
  };

  const isRunning = activeJobStatus === "running";
  const isComplete = jobStarted && activeJobStatus === "completed";
  const totalSelected = selectedIds.size;
  const totalPages = files
    .filter((f) => selectedIds.has(f.id))
    .reduce((s, f) => s + (f.page_count || 1), 0);

  const filesDone = Object.values(fileJobProgress).filter((p) => p.done).length;

  const getFileProgress = (fileId: string): FileJobProgress | null =>
    fileJobProgress[fileId] || null;

  const getStatusColor = (file: SourceFile) => {
    const p = getFileProgress(file.id);
    if (p && !p.done) return "text-indigo-500";
    if (p && p.done) return "text-emerald-500";
    if (file.status === "completed") return "text-emerald-500";
    if (file.status === "error") return "text-rose-500";
    if (file.status === "processing") return "text-indigo-500";
    return "text-slate-400";
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl w-full max-w-2xl shadow-2xl flex flex-col max-h-[90vh] overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-amber-50 dark:bg-amber-500/15 border border-amber-200 dark:border-amber-500/30 flex items-center justify-center">
              <Layers className="w-5 h-5 text-amber-600 dark:text-amber-400" />
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-900 dark:text-slate-100">Bulk OCR Extraction</h2>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Process multiple Tamil Nadu Electoral Roll PDFs in parallel
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Job Running Banner */}
        {isRunning && (
          <div className="px-6 py-3 bg-indigo-50 dark:bg-indigo-950/50 border-b border-indigo-200 dark:border-indigo-500/30 flex items-center justify-between shrink-0">
            <div className="flex items-center gap-3">
              <Loader2 className="w-4 h-4 text-indigo-600 dark:text-indigo-400 animate-spin" />
              <div>
                <p className="text-xs font-bold text-indigo-950 dark:text-indigo-200">
                  Extraction in progress — {filesDone}/{totalSelected} files completed
                </p>
                <div className="mt-1 w-48 h-1.5 rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden">
                  <div
                    className="h-full bg-indigo-600 dark:bg-indigo-500 transition-all duration-300"
                    style={{ width: `${activeJobProgress}%` }}
                  />
                </div>
              </div>
            </div>
            <span className="text-xs font-bold text-indigo-700 dark:text-indigo-300 tabular-nums">
              {activeJobProgress.toFixed(0)}%
            </span>
          </div>
        )}

        {/* Job Complete Banner */}
        {isComplete && (
          <div className="px-6 py-3 bg-emerald-50 dark:bg-emerald-950/40 border-b border-emerald-200 dark:border-emerald-500/30 flex items-center gap-3 shrink-0">
            <CheckCircle2 className="w-5 h-5 text-emerald-500 shrink-0" />
            <div>
              <p className="text-xs font-bold text-emerald-950 dark:text-emerald-200">
                Extraction complete! All {filesDone} files processed.
              </p>
            </div>
          </div>
        )}

        {/* Body */}
        <div className="flex-1 overflow-hidden flex flex-col p-6 gap-4 min-h-0">
          {/* Template & OCR Engine Selectors */}
          <div className="grid grid-cols-2 gap-4 shrink-0">
            <div>
              <label className="text-xs font-bold text-slate-700 dark:text-slate-300 block mb-1.5">
                Target Template
              </label>
              <select
                value={templateId}
                onChange={(e) => setTemplateId(e.target.value)}
                disabled={isRunning}
                className="w-full bg-white dark:bg-slate-950 border border-slate-300 dark:border-slate-800 rounded-xl px-3.5 py-2 text-xs text-slate-900 dark:text-slate-100 focus:border-indigo-500 outline-none disabled:opacity-50"
              >
                {TEMPLATES.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs font-bold text-slate-700 dark:text-slate-300 block mb-1.5">
                OCR Engine Provider
              </label>
              <select
                value={ocrEngine}
                onChange={(e) => setOcrEngine(e.target.value)}
                disabled={isRunning}
                className="w-full bg-white dark:bg-slate-950 border border-slate-300 dark:border-slate-800 rounded-xl px-3.5 py-2 text-xs text-slate-900 dark:text-slate-100 focus:border-indigo-500 outline-none disabled:opacity-50 font-medium"
              >
                {OCR_ENGINES.map((eng) => (
                  <option key={eng.id} value={eng.id}>
                    {eng.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* File List */}
          <div className="flex-1 overflow-y-auto min-h-0 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/40 divide-y divide-slate-200/60 dark:divide-slate-800/60">
            <div className="px-4 py-2.5 flex items-center gap-3 bg-slate-100/80 dark:bg-slate-900/50 sticky top-0 z-10">
              <input
                type="checkbox"
                id="select-all"
                checked={selectedIds.size === files.length && files.length > 0}
                onChange={toggleAll}
                className="rounded border-slate-300 dark:border-slate-700 text-indigo-600 focus:ring-0 cursor-pointer"
              />
              <label htmlFor="select-all" className="text-xs font-bold text-slate-700 dark:text-slate-300 cursor-pointer">
                Select All ({files.length} files)
              </label>
            </div>

            {files.map((file) => {
              const progress = getFileProgress(file.id);
              const pct = progress && progress.pagesTotal > 0
                ? ((progress.pagesCompleted + progress.pagesFailed) / progress.pagesTotal) * 100
                : 0;

              return (
                <div
                  key={file.id}
                  className={`px-4 py-3 flex items-center gap-3 transition-colors ${
                    selectedIds.has(file.id) ? "bg-indigo-50/50 dark:bg-indigo-950/20" : "hover:bg-slate-100/50 dark:hover:bg-slate-900/30"
                  }`}
                >
                  <input
                    type="checkbox"
                    id={`file-${file.id}`}
                    checked={selectedIds.has(file.id)}
                    onChange={() => toggleFile(file.id)}
                    disabled={isRunning}
                    className="rounded border-slate-300 dark:border-slate-700 text-indigo-600 focus:ring-0 cursor-pointer disabled:opacity-50"
                  />
                  <FileText className={`w-4 h-4 shrink-0 ${getStatusColor(file)}`} />

                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-semibold text-slate-800 dark:text-slate-200 truncate">{file.name}</div>
                    <div className="flex items-center gap-3 mt-0.5">
                      <span className="text-[10px] text-slate-400">{file.page_count} page(s)</span>
                      <span className={`text-[10px] capitalize font-semibold ${getStatusColor(file)}`}>
                        {progress && !progress.done ? "extracting…" : file.status}
                      </span>
                    </div>

                    {progress && !progress.done && (
                      <div className="mt-1.5 w-full h-1.5 rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden">
                        <div
                          className="h-full bg-indigo-600 dark:bg-indigo-500 transition-all duration-200"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    )}
                  </div>

                  <div className="shrink-0">
                    {progress && !progress.done && (
                      <Loader2 className="w-4 h-4 text-indigo-500 animate-spin" />
                    )}
                    {progress && progress.done && (
                      <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                    )}
                    {!progress && file.status === "completed" && (
                      <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                    )}
                    {!progress && file.status === "error" && (
                      <AlertTriangle className="w-4 h-4 text-rose-500" />
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-slate-200 dark:border-slate-800 bg-slate-50/80 dark:bg-slate-950 flex items-center justify-between shrink-0">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-xl bg-slate-200 dark:bg-slate-800 hover:bg-slate-300 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 text-xs font-bold transition-colors"
          >
            {isComplete ? "Done" : "Cancel"}
          </button>

          <button
            onClick={handleStart}
            disabled={isRunning || isStarting || !selectedIds.size}
            className="px-6 py-2 rounded-xl bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-white text-xs font-bold flex items-center gap-2 shadow-md shadow-amber-600/20 transition-all"
          >
            {isRunning || isStarting ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Zap className="w-4 h-4" />
            )}
            {isRunning
              ? `Extracting… ${activeJobProgress.toFixed(0)}%`
              : isStarting
              ? "Starting…"
              : `Extract ${totalSelected} File${totalSelected !== 1 ? "s" : ""} (${totalPages} pages)`}
          </button>
        </div>
      </div>
    </div>
  );
};

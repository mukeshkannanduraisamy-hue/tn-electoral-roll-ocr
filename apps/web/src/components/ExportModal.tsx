"use client";

import React, { useState, useEffect } from "react";
import {
  Download,
  X,
  FileSpreadsheet,
  FileText,
  Code,
  Table as TableIcon,
} from "lucide-react";
import { ExportFormat, ExportMode, ExportRequest } from "@ocr/shared-types";
import { useOcrStore } from "@/store/useOcrStore";
import { previewExport, triggerDownloadExport } from "@/lib/api";
import { toast } from "sonner";

interface ExportModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const ExportModal: React.FC<ExportModalProps> = ({ isOpen, onClose }) => {
  const { activeFileId } = useOcrStore();
  const [exportScope, setExportScope] = useState<"active" | "all">("all");
  const [format, setFormat] = useState<ExportFormat>("xlsx");
  const [mode, setMode] = useState<ExportMode>("all");
  const [includePageNumbers, setIncludePageNumbers] = useState(true);
  const [includeConfidence, setIncludeConfidence] = useState(false);
  const [includeIssues, setIncludeIssues] = useState(false);

  const [previewData, setPreviewData] = useState<{
    columns: string[];
    rows: string[][];
    total_rows: number;
  } | null>(null);
  const [isExporting, setIsExporting] = useState(false);

  const requestPayload: ExportRequest = {
    format,
    mode,
    file_ids: exportScope === "active" && activeFileId ? [activeFileId] : [],
    page_ids: [],
    record_ids: [],
    include_page_numbers: includePageNumbers,
    include_confidence: includeConfidence,
    include_issues: includeIssues,
  };

  useEffect(() => {
    if (!isOpen) return;
    previewExport(requestPayload)
      .then((res) => setPreviewData(res))
      .catch(() =>
        setPreviewData({
          columns: [
            "வரிசை எண் (S.No)",
            "அடையாள அட்டை எண் (EPIC ID)",
            "பெயர் (Name)",
            "உறவு முறை (Relation)",
            "உறவினரின் பெயர் (Relation Name)",
            "வீட்டு எண் (House No)",
            "வயது (Age)",
            "பாலினம் (Gender)",
          ],
          rows: [],
          total_rows: 0,
        })
      );
  }, [isOpen, exportScope, format, mode, includePageNumbers, includeConfidence, includeIssues, activeFileId]);

  if (!isOpen) return null;

  const handleDownload = async () => {
    try {
      setIsExporting(true);
      await triggerDownloadExport(requestPayload);
      toast.success(`Export file (${format.toUpperCase()}) generated and downloaded!`);
      onClose();
    } catch (e) {
      console.error(e);
      toast.error("Export file generation failed");
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl w-full max-w-4xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/30 flex items-center justify-center">
              <Download className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-900 dark:text-slate-100">Export Extracted Voter Data</h2>
              <p className="text-xs text-slate-500 dark:text-slate-400">Download formatted dataset with Tamil column headers</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Export Scope */}
          <div className="space-y-2">
            <label className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Export Scope
            </label>
            <div className="grid grid-cols-2 gap-3 bg-slate-100 dark:bg-slate-950 p-1.5 rounded-xl border border-slate-200 dark:border-slate-800">
              <button
                onClick={() => setExportScope("all")}
                className={`py-2 px-3 text-xs font-bold rounded-lg flex items-center justify-center gap-2 transition-all ${
                  exportScope === "all"
                    ? "bg-white dark:bg-indigo-600 text-indigo-600 dark:text-white shadow-sm"
                    : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200"
                }`}
              >
                <TableIcon className="w-4 h-4" />
                All Files in Workspace (Bulk Export)
              </button>
              <button
                onClick={() => setExportScope("active")}
                className={`py-2 px-3 text-xs font-bold rounded-lg flex items-center justify-center gap-2 transition-all ${
                  exportScope === "active"
                    ? "bg-white dark:bg-indigo-600 text-indigo-600 dark:text-white shadow-sm"
                    : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200"
                }`}
              >
                <FileText className="w-4 h-4" />
                Selected / Active File Only
              </button>
            </div>
          </div>

          {/* Format Picker */}
          <div className="space-y-2">
            <label className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Select Export Format
            </label>
            <div className="grid grid-cols-5 gap-3">
              {[
                { id: "xlsx", label: "Excel (.xlsx)", icon: FileSpreadsheet },
                { id: "csv", label: "CSV (.csv)", icon: FileText },
                { id: "json", label: "JSON (.json)", icon: Code },
                { id: "txt", label: "Text (.txt)", icon: FileText },
                { id: "md", label: "Markdown (.md)", icon: TableIcon },
              ].map((f) => {
                const Icon = f.icon;
                const isSelected = format === f.id;
                return (
                  <button
                    key={f.id}
                    onClick={() => setFormat(f.id as ExportFormat)}
                    className={`p-3.5 rounded-xl border text-xs font-bold flex flex-col items-center gap-2 transition-all ${
                      isSelected
                        ? "bg-indigo-50 dark:bg-indigo-600/20 border-indigo-500 text-indigo-600 dark:text-indigo-200 shadow-sm"
                        : "bg-slate-50/50 dark:bg-slate-950/50 border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
                    }`}
                  >
                    <Icon className="w-5 h-5" />
                    <span>{f.label}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Export Mode */}
          <div className="space-y-2">
            <label className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Export Mode
            </label>
            <div className="grid grid-cols-3 gap-3">
              {[
                { id: "all", label: "All Records", desc: "Exports every extracted voter record" },
                { id: "clean", label: "Clean Records Only", desc: "Only records with zero validation errors" },
                { id: "audit", label: "Full Audit Mode", desc: "Side-by-side original vs edited comparison" },
              ].map((m) => {
                const isSelected = mode === m.id;
                return (
                  <button
                    key={m.id}
                    onClick={() => setMode(m.id as ExportMode)}
                    className={`p-3.5 rounded-xl border text-left transition-all ${
                      isSelected
                        ? "bg-indigo-50 dark:bg-indigo-600/20 border-indigo-500 text-indigo-900 dark:text-indigo-200 shadow-xs"
                        : "bg-slate-50/50 dark:bg-slate-950/50 border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
                    }`}
                  >
                    <div className="text-xs font-bold text-slate-900 dark:text-slate-100">{m.label}</div>
                    <div className="text-[11px] text-slate-500 dark:text-slate-400 mt-1">{m.desc}</div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Live Preview Table */}
          {previewData && (
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
                <span className="font-bold uppercase tracking-wider">
                  Live Export Preview ({previewData.total_rows} total rows)
                </span>
              </div>
              <div className="max-h-48 overflow-auto border border-slate-200 dark:border-slate-800 rounded-xl bg-slate-50 dark:bg-slate-950">
                <table className="w-full text-left text-xs border-collapse">
                  <thead className="bg-slate-100 dark:bg-slate-900 sticky top-0 text-[11px] font-bold text-slate-600 dark:text-slate-400 border-b border-slate-200 dark:border-slate-800">
                    <tr>
                      {previewData.columns.map((col, idx) => (
                        <th key={idx} className="p-2.5 border-r border-slate-200 dark:border-slate-800 whitespace-nowrap">
                          {col}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200/60 dark:divide-slate-800/60 text-slate-800 dark:text-slate-300 font-medium">
                    {previewData.rows.map((row, rIdx) => (
                      <tr key={rIdx}>
                        {row.map((cell, cIdx) => (
                          <td key={cIdx} className="p-2.5 border-r border-slate-200/60 dark:border-slate-800/60 whitespace-nowrap">
                            {cell}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="px-6 py-4 border-t border-slate-200 dark:border-slate-800 bg-slate-50/80 dark:bg-slate-950 flex items-center justify-between">
          <div className="text-xs text-slate-500 dark:text-slate-400 font-medium">
            {previewData ? `${previewData.total_rows} records ready for download` : ""}
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-xl bg-slate-200 dark:bg-slate-800 hover:bg-slate-300 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 text-xs font-bold transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleDownload}
              disabled={isExporting}
              className="px-6 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold flex items-center gap-2 shadow-md shadow-emerald-600/30 transition-all"
            >
              <Download className="w-4 h-4" />
              {isExporting ? "Generating..." : "Download File"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

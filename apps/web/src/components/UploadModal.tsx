"use client";

import React, { useState, useCallback } from "react";
import { useDropzone } from "react-dropzone";
import {
  Upload,
  X,
  FolderInput,
  FileText,
  Play,
  Loader2,
  CheckCircle2,
} from "lucide-react";
import { useOcrStore } from "@/store/useOcrStore";
import { uploadFiles, importFolder } from "@/lib/api";
import { toast } from "sonner";

interface UploadModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const UploadModal: React.FC<UploadModalProps> = ({ isOpen, onClose }) => {
  const { loadFiles, startBulkJob, setActiveTab: setStoreTab, setActiveFolder } = useOcrStore();

  const [activeTab, setActiveTab] = useState<"file" | "folder">("file");
  const [folderPath, setFolderPath] = useState("");
  const [recursive, setRecursive] = useState(true);
  const [autoExtract, setAutoExtract] = useState(true);
  const [isProcessing, setIsProcessing] = useState(false);
  const [phase, setPhase] = useState<"idle" | "uploading" | "extracting" | "done">("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [uploadedCount, setUploadedCount] = useState(0);

  const onDrop = useCallback((accepted: File[]) => {}, []);

  const { getRootProps, getInputProps, isDragActive, acceptedFiles } = useDropzone({
    accept: { "application/pdf": [".pdf"] },
    multiple: true,
    onDrop,
  });

  if (!isOpen) return null;

  const reset = () => {
    setPhase("idle");
    setErrorMsg(null);
    setUploadedCount(0);
    setFolderPath("");
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  const handleFileUpload = async (andExtract: boolean) => {
    if (!acceptedFiles.length) return;
    try {
      setIsProcessing(true);
      setErrorMsg(null);
      setPhase("uploading");

      const registered = await uploadFiles(Array.from(acceptedFiles));
      setUploadedCount(registered.length);
      await loadFiles();
      toast.success(`Uploaded ${registered.length} file(s)`);

      if (andExtract && registered.length > 0) {
        setPhase("extracting");
        const ids = registered.filter((f) => f.status === "pending").map((f) => f.id);
        if (ids.length > 0) {
          await startBulkJob(ids);
        }
      }

      setPhase("done");
      if (!andExtract) setTimeout(handleClose, 600);
    } catch (e: any) {
      setErrorMsg(e.message || "Upload failed");
      toast.error(e.message || "Upload failed");
      setPhase("idle");
    } finally {
      setIsProcessing(false);
    }
  };

  const handleFolderImport = async (andExtract: boolean) => {
    if (!folderPath.trim()) return;
    try {
      setIsProcessing(true);
      setErrorMsg(null);
      setPhase("uploading");

      const registered = await importFolder(folderPath.trim(), recursive);
      setUploadedCount(registered.length);
      await loadFiles();
      toast.success(`Imported ${registered.length} file(s) from folder`);

      if (andExtract && registered.length > 0) {
        setPhase("extracting");
        const ids = registered.filter((f) => f.status === "pending").map((f) => f.id);
        if (ids.length > 0) {
          await startBulkJob(ids);
        }
      }

      setPhase("done");
      if (!andExtract) setTimeout(handleClose, 600);
    } catch (e: any) {
      setErrorMsg(e.message || "Folder import failed");
      toast.error(e.message || "Folder import failed");
      setPhase("idle");
    } finally {
      setIsProcessing(false);
    }
  };

  const isDone = phase === "done";
  const isUploading = phase === "uploading";
  const isExtracting = phase === "extracting";

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl w-full max-w-lg shadow-2xl flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-indigo-50 dark:bg-indigo-500/10 border border-indigo-200 dark:border-indigo-500/30 flex items-center justify-center">
              <Upload className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-900 dark:text-slate-100">Add PDF Documents</h2>
              <p className="text-xs text-slate-500 dark:text-slate-400">Upload single/bulk files or import a local folder</p>
            </div>
          </div>
          <button onClick={handleClose} className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tab Switcher */}
        <div className="p-4 border-b border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/40">
          <div className="grid grid-cols-2 gap-2 bg-slate-200/60 dark:bg-slate-950 p-1 rounded-xl border border-slate-200 dark:border-slate-800">
            <button
              onClick={() => setActiveTab("file")}
              className={`py-2 text-xs font-bold rounded-lg flex items-center justify-center gap-2 transition-all ${
                activeTab === "file"
                  ? "bg-white dark:bg-indigo-600 text-indigo-600 dark:text-white shadow-sm"
                  : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200"
              }`}
            >
              <FileText className="w-4 h-4" />
              Upload Files
            </button>
            <button
              onClick={() => setActiveTab("folder")}
              className={`py-2 text-xs font-bold rounded-lg flex items-center justify-center gap-2 transition-all ${
                activeTab === "folder"
                  ? "bg-white dark:bg-indigo-600 text-indigo-600 dark:text-white shadow-sm"
                  : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200"
              }`}
            >
              <FolderInput className="w-4 h-4" />
              Import Folder
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="p-6 space-y-4">
          {errorMsg && (
            <div className="p-3.5 rounded-xl bg-rose-50 dark:bg-rose-500/10 border border-rose-200 dark:border-rose-500/30 text-rose-700 dark:text-rose-300 text-xs font-medium">
              {errorMsg}
            </div>
          )}

          {(isUploading || isExtracting || isDone) && (
            <div className={`p-3.5 rounded-xl border flex items-center gap-3 text-xs ${
              isDone
                ? "bg-emerald-50 dark:bg-emerald-500/10 border-emerald-200 dark:border-emerald-500/30 text-emerald-800 dark:text-emerald-300"
                : "bg-indigo-50 dark:bg-indigo-500/10 border-indigo-200 dark:border-indigo-500/30 text-indigo-800 dark:text-indigo-300"
            }`}>
              {isDone ? (
                <CheckCircle2 className="w-5 h-5 text-emerald-500 shrink-0" />
              ) : (
                <Loader2 className="w-5 h-5 text-indigo-500 animate-spin shrink-0" />
              )}
              <div>
                {isUploading && <p className="font-bold">Registering PDFs…</p>}
                {isExtracting && (
                  <p className="font-bold">
                    OCR extraction started for {uploadedCount} file(s)…
                  </p>
                )}
                {isDone && (
                  <p className="font-bold">
                    {uploadedCount} file(s) registered successfully!
                  </p>
                )}
              </div>
            </div>
          )}

          {activeTab === "file" ? (
            <div className="space-y-4">
              <div
                {...getRootProps()}
                className={`border-2 border-dashed rounded-2xl p-8 text-center cursor-pointer transition-all flex flex-col items-center gap-3 ${
                  isDragActive
                    ? "border-indigo-500 bg-indigo-50 dark:bg-indigo-500/10"
                    : "border-slate-300 dark:border-slate-800 hover:border-slate-400 dark:hover:border-slate-700 bg-slate-50/50 dark:bg-slate-950/40"
                }`}
              >
                <input {...getInputProps()} />
                <div className="w-12 h-12 rounded-full bg-indigo-50 dark:bg-indigo-500/10 border border-indigo-200 dark:border-indigo-500/30 flex items-center justify-center text-indigo-600 dark:text-indigo-400 shadow-xs">
                  <Upload className="w-6 h-6" />
                </div>
                <div>
                  <p className="text-xs font-bold text-slate-800 dark:text-slate-200">
                    Drag & drop PDFs here, or click to browse
                  </p>
                  <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-1">
                    Supports Tamil Nadu Electoral Roll PDFs (SIR Final Roll)
                  </p>
                </div>
              </div>

              {acceptedFiles.length > 0 && (
                <div className="max-h-28 overflow-auto space-y-1.5 p-3 rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800">
                  {acceptedFiles.map((f, i) => (
                    <div key={i} className="text-xs text-slate-700 dark:text-slate-300 truncate flex items-center gap-2 font-medium">
                      <FileText className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                      {f.name}
                      <span className="text-slate-400 ml-auto shrink-0 text-[10px]">
                        {(f.size / (1024 * 1024)).toFixed(1)} MB
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-4">
              <div className="space-y-1.5">
                <label className="text-xs font-bold text-slate-700 dark:text-slate-300 block">
                  Local Absolute Folder Path
                </label>
                <input
                  type="text"
                  placeholder={`e.g. D:\\OCR\\PDF\\2026-EROLLGEN-S22-57-SIR-FinalRoll-Revision1-TAM-10-WI`}
                  value={folderPath}
                  onChange={(e) => setFolderPath(e.target.value)}
                  className="w-full bg-white dark:bg-slate-950 border border-slate-300 dark:border-slate-800 rounded-xl px-3.5 py-2.5 text-xs text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 outline-none font-mono"
                />
              </div>
              <div className="flex items-center justify-between">
                <label className="flex items-center gap-2 text-xs text-slate-700 dark:text-slate-300 cursor-pointer font-medium">
                  <input
                    type="checkbox"
                    checked={recursive}
                    onChange={(e) => setRecursive(e.target.checked)}
                    className="rounded border-slate-300 dark:border-slate-700 text-indigo-600 focus:ring-0 cursor-pointer"
                  />
                  Include subdirectories recursively
                </label>

                <button
                  type="button"
                  onClick={() => {
                    if (folderPath.trim()) setActiveFolder(folderPath.trim());
                    setStoreTab("folder_ocr");
                    handleClose();
                  }}
                  className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline font-semibold"
                >
                  Open in Folder OCR View →
                </button>
              </div>
            </div>
          )}

          <label className="flex items-center gap-3 p-3.5 rounded-xl bg-indigo-50/50 dark:bg-indigo-950/30 border border-indigo-200 dark:border-indigo-500/20 cursor-pointer hover:border-indigo-300 dark:hover:border-indigo-500/40 transition-colors">
            <input
              type="checkbox"
              checked={autoExtract}
              onChange={(e) => setAutoExtract(e.target.checked)}
              className="rounded border-slate-300 dark:border-slate-700 text-indigo-600 focus:ring-0 cursor-pointer"
            />
            <div>
              <p className="text-xs font-bold text-indigo-950 dark:text-indigo-200 flex items-center gap-1.5">
                <Play className="w-3.5 h-3.5 text-indigo-600 dark:text-indigo-400" />
                Auto-start OCR extraction after import
              </p>
              <p className="text-[11px] text-indigo-700/70 dark:text-indigo-400/80 mt-0.5">
                Queues OCR processing immediately after registration
              </p>
            </div>
          </label>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-slate-200 dark:border-slate-800 bg-slate-50/80 dark:bg-slate-950 flex items-center justify-end gap-3">
          <button
            onClick={handleClose}
            className="px-4 py-2 rounded-xl bg-slate-200 dark:bg-slate-800 hover:bg-slate-300 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 text-xs font-bold transition-colors"
          >
            {isDone ? "Close" : "Cancel"}
          </button>
          <button
            onClick={() =>
              activeTab === "file"
                ? handleFileUpload(autoExtract)
                : handleFolderImport(autoExtract)
            }
            disabled={
              isProcessing ||
              (activeTab === "file" && !acceptedFiles.length) ||
              (activeTab === "folder" && !folderPath.trim())
            }
            className="px-5 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs font-bold flex items-center gap-2 shadow-md shadow-indigo-600/30 transition-all"
          >
            {isProcessing ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Upload className="w-4 h-4" />
            )}
            {isProcessing
              ? isExtracting
                ? "Extracting…"
                : "Uploading…"
              : autoExtract
              ? activeTab === "file"
                ? "Upload & Extract"
                : "Import & Extract"
              : activeTab === "file"
              ? "Upload Files"
              : "Import Folder"}
          </button>
        </div>
      </div>
    </div>
  );
};

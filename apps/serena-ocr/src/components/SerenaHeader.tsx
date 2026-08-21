"use client";

import React, { useRef } from "react";
import {
  Folder,
  FolderOpen,
  RefreshCw,
  Loader2,
  Sparkles,
  Layers,
  Shield,
  LogOut,
  Sliders,
  Database,
  Cpu,
  Sun,
  Moon,
  CheckCircle2,
  Zap,
  Rocket,
} from "lucide-react";
import { useSerenaStore } from "@/store/useSerenaStore";
import { uploadFiles } from "@/lib/api";
import { toast } from "sonner";

const PRESETS = [
  { label: "Penn PDF (47 Parts)", path: "D:\\OCR\\PDF\\Penn PDF" },
  { label: "Part 10", path: "D:\\OCR\\PDF\\2026-EROLLGEN-S22-57-SIR-FinalRoll-Revision1-TAM-10-WI" },
  { label: "Part 11", path: "D:\\OCR\\PDF\\2026-EROLLGEN-S22-57-SIR-FinalRoll-Revision1-TAM-11-WI" },
  { label: "Part 12", path: "D:\\OCR\\PDF\\2026-EROLLGEN-S22-57-SIR-FinalRoll-Revision1-TAM-12-WI" },
  { label: "Part 13", path: "D:\\OCR\\PDF\\2026-EROLLGEN-S22-57-SIR-FinalRoll-Revision1-TAM-13-WI" },
  { label: "Part 14", path: "D:\\OCR\\PDF\\2026-EROLLGEN-S22-57-SIR-FinalRoll-Revision1-TAM-14-WI" },
  { label: "All PDF Root", path: "D:\\OCR\\PDF" },
];

export const SerenaHeader: React.FC<{ onOpenAuth: () => void }> = ({ onOpenAuth }) => {
  const {
    folderPath,
    setFolderPath,
    recursive,
    setRecursive,
    isScanning,
    scanCurrentFolder,
    templateId,
    setTemplateId,
    user,
    logout,
    theme,
    toggleTheme,
    activeTab,
    setActiveTab,
    autoInsertToDb,
    toggleAutoInsertToDb,
  } = useSerenaStore();

  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDirectoryUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    const pdfs = Array.from(files).filter((f) => f.name.toLowerCase().endsWith(".pdf"));
    if (pdfs.length === 0) {
      toast.error("No PDF documents found in selected folder");
      return;
    }

    toast.info(`Uploading & registering ${pdfs.length} PDF(s)...`);
    try {
      await uploadFiles(pdfs);
      await useSerenaStore.getState().loadDbFiles();
      toast.success(`Successfully uploaded ${pdfs.length} PDFs!`);
      void scanCurrentFolder();
    } catch (err: any) {
      toast.error(err?.message || "Failed to upload folder");
    } finally {
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  return (
    <header className="px-6 py-4 border-b border-slate-200 dark:border-white/5 bg-white/80 dark:bg-obsidian-900/80 backdrop-blur-2xl flex flex-col gap-3 shrink-0">
      {/* Top Identity & Navigation Row */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        {/* Logo & Brand */}
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-serena-indigo via-serena-violet to-serena-rose p-0.5 shadow-lg shadow-serena-indigo/20">
            <div className="w-full h-full bg-white dark:bg-obsidian-950 rounded-[14px] flex items-center justify-center">
              <Layers className="w-5 h-5 text-serena-indigo" />
            </div>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold tracking-tight text-slate-900 dark:text-white">
                Serena OCR Explorer
              </span>
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20 font-semibold">
                Tamil Nadu
              </span>
            </div>
            <p className="text-[11px] text-slate-500 dark:text-slate-400">
              Electoral Roll Batch OCR & Curated Voter Database
            </p>
          </div>
        </div>

        {/* Center Primary Page Switcher Tabs */}
        <div className="flex items-center gap-1 bg-slate-200/70 dark:bg-white/5 p-1 rounded-xl border border-slate-300 dark:border-white/10">
          <button
            onClick={() => setActiveTab("workstation")}
            className={`px-3 py-1 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all ${
              activeTab === "workstation"
                ? "bg-white dark:bg-blue-600 text-blue-600 dark:text-white shadow-xs font-bold"
                : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
            }`}
          >
            <Folder className="w-3.5 h-3.5 text-amber-500 fill-amber-500" />
            <span>Files Explorer</span>
          </button>

          <button
            onClick={() => setActiveTab("database")}
            className={`px-3 py-1 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all ${
              activeTab === "database"
                ? "bg-white dark:bg-blue-600 text-blue-600 dark:text-white shadow-xs font-bold"
                : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
            }`}
          >
            <Database className="w-3.5 h-3.5" />
            <span>Database</span>
          </button>

          <button
            onClick={() => setActiveTab("deployment")}
            className={`px-3 py-1 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all ${
              activeTab === "deployment"
                ? "bg-white dark:bg-blue-600 text-blue-600 dark:text-white shadow-xs font-bold"
                : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
            }`}
          >
            <Rocket className="w-3.5 h-3.5" />
            <span>Deployment</span>
          </button>
        </div>

        {/* Right Station Controls, Auto-DB status, Theme Toggle & Auth */}
        <div className="flex items-center gap-2.5">
          {/* Auto DB Insert Toggle */}
          <button
            onClick={toggleAutoInsertToDb}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold border transition-all ${
              autoInsertToDb
                ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:text-emerald-400"
                : "bg-slate-100 dark:bg-obsidian-950 border-slate-200 dark:border-white/10 text-slate-400"
            }`}
            title="Auto-insert extracted voter records directly into SQLite database"
          >
            <Zap className={`w-3.5 h-3.5 ${autoInsertToDb ? "text-emerald-500 fill-emerald-500 animate-pulse" : "text-slate-400"}`} />
            <span className="hidden sm:inline">Auto DB Insert:</span>
            <span className="font-bold">{autoInsertToDb ? "ON" : "OFF"}</span>
          </button>

          {/* Template Selector */}
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-100 dark:bg-obsidian-950 border border-slate-200 dark:border-white/10 text-xs text-slate-700 dark:text-slate-300">
            <Sliders className="w-3.5 h-3.5 text-serena-violet" />
            <span className="text-slate-400 dark:text-slate-500 font-medium">Template:</span>
            <select
              value={templateId}
              onChange={(e) => setTemplateId(e.target.value)}
              className="bg-transparent text-slate-800 dark:text-slate-200 font-semibold outline-none cursor-pointer pr-1"
            >
              <option value="auto" className="bg-white dark:bg-obsidian-900">Auto-Detect</option>
              <option value="standard" className="bg-white dark:bg-obsidian-900">Tamil Nadu Standard (30-Box)</option>
              <option value="supplement" className="bg-white dark:bg-obsidian-900">Supplement Format</option>
            </select>
          </div>

          {/* Theme Toggle Button */}
          <button
            onClick={toggleTheme}
            className="p-2 rounded-xl bg-slate-100 dark:bg-obsidian-950 hover:bg-slate-200 dark:hover:bg-obsidian-850 border border-slate-200 dark:border-white/10 text-slate-700 dark:text-slate-300 transition-colors shadow-xs"
            title={`Switch to ${theme === "dark" ? "Light" : "Dark"} theme`}
          >
            {theme === "dark" ? (
              <Sun className="w-4 h-4 text-amber-400" />
            ) : (
              <Moon className="w-4 h-4 text-serena-indigo" />
            )}
          </button>

          {/* User / Login Button */}
          {user ? (
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-100 dark:bg-obsidian-950 border border-emerald-500/30 text-xs">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              <span className="font-bold text-emerald-600 dark:text-emerald-300">{user.username || "Admin"}</span>
              <button
                onClick={() => void logout()}
                className="text-slate-400 hover:text-rose-500 transition-colors ml-1"
                title="Sign out"
              >
                <LogOut className="w-3.5 h-3.5" />
              </button>
            </div>
          ) : (
            <button
              onClick={onOpenAuth}
              className="px-3.5 py-1.5 rounded-xl bg-slate-100 dark:bg-obsidian-950 hover:bg-slate-200 dark:hover:bg-obsidian-850 border border-slate-200 dark:border-white/10 text-xs font-semibold text-slate-700 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white flex items-center gap-1.5 transition-all shadow-xs"
            >
              <Shield className="w-3.5 h-3.5 text-serena-indigo" />
              <span>Sign In</span>
            </button>
          )}
        </div>
      </div>

      {/* Directory Selector Bar (Only in Workstation Tab) */}
      {activeTab === "workstation" && (
        <>
          <div className="flex items-center gap-2.5 flex-wrap pt-1">
            <div className="relative flex-1 min-w-[280px]">
              <Folder className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-serena-indigo pointer-events-none" />
              <input
                type="text"
                value={folderPath}
                onChange={(e) => setFolderPath(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void scanCurrentFolder();
                }}
                placeholder="Enter local folder path (e.g. D:\OCR\PDF\Penn PDF)"
                className="w-full pl-10 pr-4 py-2.5 bg-slate-50 dark:bg-obsidian-950/90 border border-slate-200 dark:border-white/10 rounded-xl text-xs font-mono text-slate-900 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-serena-indigo/40 focus:border-serena-indigo/60 transition-all shadow-inner"
              />
            </div>

            <label className="flex items-center gap-2 px-3.5 py-2.5 rounded-xl bg-slate-50 dark:bg-obsidian-950 border border-slate-200 dark:border-white/10 text-xs text-slate-700 dark:text-slate-300 font-medium cursor-pointer hover:bg-slate-100 dark:hover:bg-obsidian-850 transition-colors">
              <input
                type="checkbox"
                checked={recursive}
                onChange={(e) => setRecursive(e.target.checked)}
                className="rounded border-slate-400 dark:border-slate-700 text-serena-indigo focus:ring-0 cursor-pointer"
              />
              <span>Scan Subfolders</span>
            </label>

            <button
              onClick={() => void scanCurrentFolder()}
              disabled={isScanning}
              className="px-4 py-2.5 rounded-xl bg-gradient-to-r from-serena-indigo to-serena-violet hover:from-indigo-500 hover:to-violet-500 disabled:opacity-50 text-white text-xs font-bold flex items-center gap-2 shadow-lg shadow-serena-indigo/25 transition-all active:scale-95"
            >
              {isScanning ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <RefreshCw className="w-4 h-4" />
              )}
              <span>{isScanning ? "Scanning Folder…" : "Scan Folder"}</span>
            </button>

            {/* Hidden native folder picker */}
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleDirectoryUpload}
              // @ts-ignore
              webkitdirectory="true"
              directory="true"
              multiple
              className="hidden"
            />

            <button
              onClick={() => fileInputRef.current?.click()}
              className="px-3.5 py-2.5 rounded-xl bg-slate-50 dark:bg-obsidian-950 hover:bg-slate-100 dark:hover:bg-obsidian-850 border border-slate-200 dark:border-white/10 text-slate-700 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white text-xs font-semibold flex items-center gap-2 transition-all shadow-xs"
              title="Browse local directory via file explorer"
            >
              <FolderOpen className="w-4 h-4 text-serena-amber" />
              <span className="hidden sm:inline">Browse Folder</span>
            </button>
          </div>

          {/* Preset Quick Chips */}
          <div className="flex items-center gap-1.5 overflow-x-auto pb-0.5 text-xs no-scrollbar">
            <span className="text-[11px] text-slate-400 dark:text-slate-500 font-semibold uppercase tracking-wider shrink-0 mr-1">
              Quick Presets:
            </span>
            {PRESETS.map((p) => {
              const isSelected = folderPath === p.path;
              return (
                <button
                  key={p.path}
                  onClick={() => {
                    setFolderPath(p.path);
                    void scanCurrentFolder(p.path);
                  }}
                  className={`px-2.5 py-1 rounded-lg text-xs font-medium whitespace-nowrap transition-all flex items-center gap-1.5 ${
                    isSelected
                      ? "bg-serena-indigo/15 text-serena-indigo border border-serena-indigo/40 shadow-xs font-bold"
                      : "bg-slate-100 dark:bg-obsidian-950 hover:bg-slate-200 dark:hover:bg-obsidian-850 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 border border-slate-200 dark:border-white/5"
                  }`}
                >
                  <Folder className="w-3 h-3 text-serena-indigo/80" />
                  {p.label}
                </button>
              );
            })}
          </div>
        </>
      )}
    </header>
  );
};

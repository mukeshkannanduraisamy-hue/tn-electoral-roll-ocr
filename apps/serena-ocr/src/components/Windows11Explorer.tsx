"use client";

import React, { useState, useMemo, useRef } from "react";
import {
  Folder,
  FolderOpen,
  FileText,
  Search,
  RefreshCw,
  Zap,
  RotateCcw,
  CheckSquare,
  Square,
  CheckCircle2,
  Clock,
  AlertTriangle,
  Loader2,
  HardDrive,
  LayoutGrid,
  List,
  ChevronRight,
  ChevronDown,
  Database,
  Download,
  Info,
  ChevronLeft,
  ArrowUp,
  X,
  Sparkles,
  Plus,
  ArrowUpDown,
  MoreHorizontal,
  Minus,
  Square as WindowSquare,
  PanelRight,
  SlidersHorizontal,
  Copy,
  Trash2,
  Share2,
  Edit3,
  Scissors,
  Check,
  Star,
  Monitor,
  Cloud,
  Layers,
  Rocket,
  Sun,
  Moon,
  ExternalLink,
  ShieldCheck,
} from "lucide-react";
import { useSerenaStore } from "@/store/useSerenaStore";
import { FolderPdfItem } from "@/types";
import { toast } from "sonner";
import { DatabasePage } from "./DatabasePage";
import { LocalDeploymentPage } from "./LocalDeploymentPage";

export const Windows11Explorer: React.FC<{ onOpenAuth: () => void }> = ({ onOpenAuth }) => {
  const {
    folderPath,
    setFolderPath,
    scanCurrentFolder,
    scannedData,
    isScanning,
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
    processSingle,
    reprocessSingle,
    processSelected,
    reprocessSelected,
    processAllUnprocessed,
    actionInProgress,
    activeJobStatus,
    activeJobProgress,
    pagesPerSec,
    etaSeconds,
    cancelActiveJob,
    autoInsertToDb,
    toggleAutoInsertToDb,
    activeTab,
    setActiveTab,
    theme,
    toggleTheme,
    user,
    logout,
    liveExtractedElectors,
  } = useSerenaStore();

  const [viewStyle, setViewStyle] = useState<"details" | "tiles" | "large_icons">("details");
  const [showDetailsPane, setShowDetailsPane] = useState(true);
  const [isEditingPath, setIsEditingPath] = useState(false);
  const [pathInput, setPathInput] = useState(folderPath);
  const [sortBy, setSortBy] = useState<"name" | "date" | "size" | "status" | "records">("name");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("asc");
  const [expandedNodes, setExpandedNodes] = useState<Record<string, boolean>>({
    quickAccess: true,
    thisPc: true,
    diskD: true,
    ocrFolder: true,
    dbSection: true,
  });

  const fileInputRef = useRef<HTMLInputElement>(null);
  const isJobRunning = activeJobStatus === "running";

  const toggleNode = (node: string) => {
    setExpandedNodes((prev) => ({ ...prev, [node]: !prev[node] }));
  };

  // Filter & Sort Items
  const filteredItems = useMemo(() => {
    if (!scannedData?.items) return [];
    let items = scannedData.items.filter((item) => {
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

    items.sort((a, b) => {
      let cmp = 0;
      if (sortBy === "name") cmp = a.name.localeCompare(b.name, undefined, { numeric: true });
      else if (sortBy === "size") cmp = a.size_bytes - b.size_bytes;
      else if (sortBy === "status") cmp = a.status.localeCompare(b.status);
      else if (sortBy === "records") cmp = (a.records_count || 0) - (b.records_count || 0);
      return sortOrder === "asc" ? cmp : -cmp;
    });

    return items;
  }, [scannedData, searchQuery, statusFilter, sortBy, sortOrder]);

  const stats = useMemo(() => {
    const total = scannedData?.items?.length || 0;
    const completed = scannedData?.items?.filter((i) => i.status === "completed").length || 0;
    const pending = total - completed;
    return { total, completed, pending };
  }, [scannedData]);

  const handleFolderSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (pathInput.trim()) {
      setFolderPath(pathInput.trim());
      void scanCurrentFolder(pathInput.trim());
      setIsEditingPath(false);
    }
  };

  const handleSelectFolderDialog = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      const firstFile = files[0];
      const relativePath = firstFile.webkitRelativePath;
      if (relativePath) {
        const folderName = relativePath.split("/")[0];
        const newPath = folderPath.includes(":")
          ? `${folderPath.substring(0, folderPath.lastIndexOf("\\") + 1)}${folderName}`
          : folderName;
        setFolderPath(newPath);
        setPathInput(newPath);
        void scanCurrentFolder(newPath);
      }
    }
  };

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-[#F3F3F3] dark:bg-[#1E1E1E] text-slate-800 dark:text-slate-100 font-sans select-none antialiased">
      {/* ========================================================================= */}
      {/* 1. WINDOWS 11 TITLE BAR & TAB BAR */}
      {/* ========================================================================= */}
      <div className="h-10 bg-[#EAEAEA] dark:bg-[#181818] flex items-center justify-between px-2 shrink-0 border-b border-black/5 dark:border-white/5">
        {/* Native Windows 11 Tabs */}
        <div className="flex items-center gap-1 h-full pt-1.5 flex-1 min-w-0">
          {/* Tab 1: File Explorer */}
          <button
            onClick={() => setActiveTab("workstation")}
            className={`h-full px-3.5 rounded-t-lg flex items-center gap-2 text-xs transition-all relative group max-w-[220px] ${
              activeTab === "workstation"
                ? "bg-white dark:bg-[#202020] text-slate-900 dark:text-white font-semibold shadow-xs border-t border-x border-slate-300 dark:border-white/10"
                : "text-slate-600 dark:text-slate-400 hover:bg-black/5 dark:hover:bg-white/5"
            }`}
          >
            <Folder className="w-3.5 h-3.5 text-amber-500 fill-amber-500 shrink-0" />
            <span className="truncate">{folderPath.split(/[\/\\]/).pop() || "Penn PDF"}</span>
            <span className="text-[10px] opacity-40 hover:opacity-100 ml-1">×</span>
          </button>

          {/* Tab 2: Database Explorer */}
          <button
            onClick={() => setActiveTab("database")}
            className={`h-full px-3.5 rounded-t-lg flex items-center gap-2 text-xs transition-all relative group max-w-[220px] ${
              activeTab === "database"
                ? "bg-white dark:bg-[#202020] text-slate-900 dark:text-white font-semibold shadow-xs border-t border-x border-slate-300 dark:border-white/10"
                : "text-slate-600 dark:text-slate-400 hover:bg-black/5 dark:hover:bg-white/5"
            }`}
          >
            <Database className="w-3.5 h-3.5 text-indigo-500 shrink-0" />
            <span className="truncate">Database Records</span>
            <span className="text-[10px] opacity-40 hover:opacity-100 ml-1">×</span>
          </button>

          {/* Tab 3: Local Deployment */}
          <button
            onClick={() => setActiveTab("deployment")}
            className={`h-full px-3.5 rounded-t-lg flex items-center gap-2 text-xs transition-all relative group max-w-[220px] ${
              activeTab === "deployment"
                ? "bg-white dark:bg-[#202020] text-slate-900 dark:text-white font-semibold shadow-xs border-t border-x border-slate-300 dark:border-white/10"
                : "text-slate-600 dark:text-slate-400 hover:bg-black/5 dark:hover:bg-white/5"
            }`}
          >
            <Rocket className="w-3.5 h-3.5 text-purple-500 shrink-0" />
            <span className="truncate">Deployment Center</span>
            <span className="text-[10px] opacity-40 hover:opacity-100 ml-1">×</span>
          </button>

          {/* New Tab Button */}
          <button
            onClick={() => setActiveTab("workstation")}
            className="w-7 h-7 rounded hover:bg-black/5 dark:hover:bg-white/10 flex items-center justify-center text-slate-500 text-sm font-bold"
            title="Open new tab"
          >
            <Plus className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Windows Controls (Theme, Auth, Minimize, Maximize, Close) */}
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={toggleTheme}
            className="w-8 h-7 rounded hover:bg-black/5 dark:hover:bg-white/10 flex items-center justify-center text-slate-600 dark:text-slate-400"
            title="Toggle Light / Dark Mica"
          >
            {theme === "dark" ? <Sun className="w-3.5 h-3.5 text-amber-400" /> : <Moon className="w-3.5 h-3.5" />}
          </button>

          {user ? (
            <button
              onClick={() => void logout()}
              className="px-2 h-7 rounded hover:bg-black/5 dark:hover:bg-white/10 flex items-center gap-1.5 text-xs text-slate-600 dark:text-slate-300"
              title="Sign Out"
            >
              <span className="w-2 h-2 rounded-full bg-emerald-500" />
              <span className="font-medium text-[11px]">{user.username}</span>
            </button>
          ) : (
            <button
              onClick={onOpenAuth}
              className="px-2 h-7 rounded bg-blue-600 hover:bg-blue-700 text-white flex items-center gap-1 text-[11px] font-semibold"
            >
              <span>Sign In</span>
            </button>
          )}

          {/* Window Buttons */}
          <div className="flex items-center ml-2 border-l border-slate-300 dark:border-white/10 pl-2">
            <button className="w-9 h-7 hover:bg-black/5 dark:hover:bg-white/10 flex items-center justify-center text-slate-500">
              <Minus className="w-3.5 h-3.5" />
            </button>
            <button className="w-9 h-7 hover:bg-black/5 dark:hover:bg-white/10 flex items-center justify-center text-slate-500">
              <WindowSquare className="w-3 h-3" />
            </button>
            <button className="w-9 h-7 hover:bg-red-600 hover:text-white flex items-center justify-center text-slate-500">
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* 2. WINDOWS 11 ADDRESS BAR & SEARCH BAR */}
      {/* ========================================================================= */}
      {activeTab === "workstation" && (
        <div className="px-3 py-1.5 bg-[#F9F9F9] dark:bg-[#202020] border-b border-slate-300 dark:border-white/10 flex items-center gap-2 shrink-0 text-xs">
          {/* Navigation Arrows */}
          <div className="flex items-center gap-0.5">
            <button className="p-1.5 rounded hover:bg-black/5 dark:hover:bg-white/10 text-slate-400 disabled:opacity-40" disabled>
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button className="p-1.5 rounded hover:bg-black/5 dark:hover:bg-white/10 text-slate-400 disabled:opacity-40" disabled>
              <ChevronRight className="w-4 h-4" />
            </button>
            <button
              onClick={() => {
                const parent = folderPath.substring(0, folderPath.lastIndexOf("\\"));
                if (parent) {
                  setFolderPath(parent);
                  setPathInput(parent);
                  void scanCurrentFolder(parent);
                }
              }}
              className="p-1.5 rounded hover:bg-black/5 dark:hover:bg-white/10 text-slate-600 dark:text-slate-300"
              title="Up to Parent Directory"
            >
              <ArrowUp className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => void scanCurrentFolder()}
              className="p-1.5 rounded hover:bg-black/5 dark:hover:bg-white/10 text-slate-600 dark:text-slate-300"
              title="Refresh (F5)"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isScanning ? "animate-spin" : ""}`} />
            </button>
          </div>

          {/* Win11 Pill Address Bar */}
          <div className="flex-1 flex items-center bg-white dark:bg-[#2C2C2C] border border-slate-300 dark:border-white/10 rounded-md px-2.5 py-1 shadow-2xs focus-within:ring-1 focus-within:ring-blue-500">
            <Folder className="w-4 h-4 text-amber-500 fill-amber-500 mr-2 shrink-0" />

            {isEditingPath ? (
              <form onSubmit={handleFolderSubmit} className="flex-1 flex items-center">
                <input
                  type="text"
                  value={pathInput}
                  onChange={(e) => setPathInput(e.target.value)}
                  onBlur={() => setIsEditingPath(false)}
                  autoFocus
                  className="w-full bg-transparent text-xs font-mono text-slate-900 dark:text-white focus:outline-none"
                />
              </form>
            ) : (
              <div
                onClick={() => {
                  setPathInput(folderPath);
                  setIsEditingPath(true);
                }}
                className="flex-1 flex items-center gap-1 text-xs font-mono text-slate-700 dark:text-slate-300 cursor-text truncate overflow-hidden"
              >
                {folderPath.split(/[\/\\]/).map((segment, idx, arr) => (
                  <React.Fragment key={idx}>
                    <span className="hover:bg-slate-100 dark:hover:bg-white/10 px-1 py-0.5 rounded cursor-pointer truncate">
                      {segment || "This PC"}
                    </span>
                    {idx < arr.length - 1 && (
                      <ChevronRight className="w-3 h-3 text-slate-400 shrink-0" />
                    )}
                  </React.Fragment>
                ))}
              </div>
            )}

            <label className="ml-1 px-2 py-0.5 rounded bg-slate-100 dark:bg-white/10 hover:bg-slate-200 dark:hover:bg-white/15 text-[11px] font-medium text-slate-700 dark:text-slate-300 cursor-pointer shrink-0">
              <span>Browse…</span>
              <input
                type="file"
                // @ts-ignore
                webkitdirectory="true"
                directory="true"
                multiple
                onChange={handleSelectFolderDialog}
                className="hidden"
              />
            </label>
          </div>

          {/* Win11 Search Box */}
          <div className="w-64 flex items-center bg-white dark:bg-[#2C2C2C] border border-slate-300 dark:border-white/10 rounded-md px-2.5 py-1 shadow-2xs focus-within:ring-1 focus-within:ring-blue-500">
            <Search className="w-3.5 h-3.5 text-slate-400 mr-2 shrink-0" />
            <input
              type="text"
              placeholder={`Search ${folderPath.split(/[\/\\]/).pop() || "Folder"}`}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-transparent text-xs text-slate-900 dark:text-white placeholder:text-slate-400 focus:outline-none"
            />
            {searchQuery && (
              <button onClick={() => setSearchQuery("")} className="text-slate-400 hover:text-slate-600">
                <X className="w-3 h-3" />
              </button>
            )}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 3. WINDOWS 11 COMMAND BAR (RIBBON) */}
      {/* ========================================================================= */}
      {activeTab === "workstation" && (
        <div className="px-3 py-1 bg-[#F9F9F9] dark:bg-[#252525] border-b border-slate-200 dark:border-white/10 flex items-center justify-between gap-2 shrink-0 text-xs flex-wrap">
          {/* Fluent Action Icons & Primary Operations */}
          <div className="flex items-center gap-1.5 flex-wrap">
            {/* Process All / Run OCR */}
            <button
              onClick={() => void processAllUnprocessed()}
              disabled={isJobRunning || stats.pending === 0}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-[#005FB8] hover:bg-[#004E98] text-white font-semibold shadow-xs disabled:opacity-50 transition-all"
            >
              <Zap className="w-3.5 h-3.5 fill-white" />
              <span>Process All ({stats.pending})</span>
            </button>

            {selectedPaths.size > 0 && (
              <>
                <button
                  onClick={() => void processSelected()}
                  disabled={isJobRunning}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-blue-600 hover:bg-blue-700 text-white font-semibold shadow-xs disabled:opacity-50 transition-all"
                >
                  <Zap className="w-3.5 h-3.5" />
                  <span>Process Selected ({selectedPaths.size})</span>
                </button>

                <button
                  onClick={() => void reprocessSelected()}
                  disabled={isJobRunning}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-slate-200 dark:bg-white/10 hover:bg-slate-300 dark:hover:bg-white/15 text-slate-800 dark:text-slate-200 font-medium transition-all"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                  <span>Re-Process</span>
                </button>
              </>
            )}

            <div className="h-4 w-[1px] bg-slate-300 dark:bg-white/10 mx-1" />

            {/* Select All */}
            <button
              onClick={toggleSelectAll}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md hover:bg-black/5 dark:hover:bg-white/5 text-slate-700 dark:text-slate-300"
            >
              {selectedPaths.size > 0 && selectedPaths.size === filteredItems.length ? (
                <CheckSquare className="w-3.5 h-3.5 text-blue-600" />
              ) : selectedPaths.size > 0 ? (
                <CheckSquare className="w-3.5 h-3.5 text-blue-600 opacity-70" />
              ) : (
                <Square className="w-3.5 h-3.5 text-slate-400" />
              )}
              <span>Select all</span>
            </button>

            {/* Sort Dropdown */}
            <div className="flex items-center gap-1 px-2 py-1 rounded-md hover:bg-black/5 dark:hover:bg-white/5 text-slate-700 dark:text-slate-300 cursor-pointer">
              <ArrowUpDown className="w-3.5 h-3.5 text-slate-500" />
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as any)}
                className="bg-transparent text-xs font-medium cursor-pointer focus:outline-none"
              >
                <option value="name" className="dark:bg-[#252525]">Sort by Name</option>
                <option value="size" className="dark:bg-[#252525]">Sort by Size</option>
                <option value="status" className="dark:bg-[#252525]">Sort by Status</option>
                <option value="records" className="dark:bg-[#252525]">Sort by Voters</option>
              </select>
            </div>
          </div>

          {/* Right View & Pane Controls */}
          <div className="flex items-center gap-2">
            {/* View Switchers */}
            <div className="flex items-center bg-slate-200/70 dark:bg-white/5 p-0.5 rounded-md border border-slate-300 dark:border-white/10">
              <button
                onClick={() => setViewStyle("details")}
                className={`p-1 rounded ${viewStyle === "details" ? "bg-white dark:bg-white/15 text-blue-600 dark:text-blue-400 shadow-2xs font-bold" : "text-slate-500"}`}
                title="Details View (Table)"
              >
                <List className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={() => setViewStyle("tiles")}
                className={`p-1 rounded ${viewStyle === "tiles" ? "bg-white dark:bg-white/15 text-blue-600 dark:text-blue-400 shadow-2xs font-bold" : "text-slate-500"}`}
                title="Tiles View (Cards)"
              >
                <LayoutGrid className="w-3.5 h-3.5" />
              </button>
            </div>

            {/* Toggle Details Pane */}
            <button
              onClick={() => setShowDetailsPane(!showDetailsPane)}
              className={`px-2 py-1 rounded-md border transition-colors flex items-center gap-1.5 ${
                showDetailsPane
                  ? "bg-blue-50 dark:bg-blue-500/10 border-blue-300 dark:border-blue-500/30 text-blue-600 dark:text-blue-400"
                  : "border-slate-300 dark:border-white/10 text-slate-600 dark:text-slate-400 hover:bg-black/5 dark:hover:bg-white/5"
              }`}
              title="Toggle Details & Preview Pane"
            >
              <PanelRight className="w-3.5 h-3.5" />
              <span className="text-[11px]">Details</span>
            </button>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 4. MAIN WORKSPACE (TAB ROUTING) */}
      {/* ========================================================================= */}
      {activeTab === "workstation" ? (
        <div className="flex-1 flex min-h-0 overflow-hidden bg-white dark:bg-[#191919]">
          {/* 4A. LEFT WINDOWS 11 NAVIGATION TREE */}
          <nav className="w-56 lg:w-64 bg-[#FBFBFB] dark:bg-[#181818] border-r border-slate-200 dark:border-white/10 p-2 flex flex-col gap-1 shrink-0 text-xs overflow-y-auto select-none">
            {/* Quick Access Node */}
            <div>
              <div
                onClick={() => toggleNode("quickAccess")}
                className="flex items-center gap-1.5 px-2 py-1 rounded hover:bg-black/5 dark:hover:bg-white/5 text-slate-700 dark:text-slate-300 font-semibold cursor-pointer"
              >
                {expandedNodes.quickAccess ? (
                  <ChevronDown className="w-3 h-3 text-slate-400" />
                ) : (
                  <ChevronRight className="w-3 h-3 text-slate-400" />
                )}
                <Star className="w-3.5 h-3.5 text-blue-500 fill-blue-500" />
                <span>Quick access</span>
              </div>

              {expandedNodes.quickAccess && (
                <div className="ml-4 pl-2 border-l border-slate-200 dark:border-white/10 space-y-0.5 mt-0.5">
                  <button
                    onClick={() => setStatusFilter("all")}
                    className={`w-full flex items-center justify-between px-2 py-1 rounded text-left ${
                      statusFilter === "all"
                        ? "bg-[#E5F3FF] dark:bg-[#003774]/40 text-[#005FB8] dark:text-blue-300 font-semibold"
                        : "hover:bg-black/5 dark:hover:bg-white/5 text-slate-700 dark:text-slate-300"
                    }`}
                  >
                    <div className="flex items-center gap-2 truncate">
                      <Folder className="w-3.5 h-3.5 text-amber-500 fill-amber-500" />
                      <span className="truncate">All PDF Rolls</span>
                    </div>
                    <span className="text-[10px] font-mono opacity-60">{stats.total}</span>
                  </button>

                  <button
                    onClick={() => setStatusFilter("completed")}
                    className={`w-full flex items-center justify-between px-2 py-1 rounded text-left ${
                      statusFilter === "completed"
                        ? "bg-emerald-100/70 dark:bg-emerald-600/20 text-emerald-700 dark:text-emerald-300 font-semibold"
                        : "hover:bg-black/5 dark:hover:bg-white/5 text-slate-700 dark:text-slate-300"
                    }`}
                  >
                    <div className="flex items-center gap-2 truncate">
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                      <span className="truncate">Completed</span>
                    </div>
                    <span className="text-[10px] font-mono text-emerald-600 dark:text-emerald-400">{stats.completed}</span>
                  </button>

                  <button
                    onClick={() => setStatusFilter("pending")}
                    className={`w-full flex items-center justify-between px-2 py-1 rounded text-left ${
                      statusFilter === "pending"
                        ? "bg-amber-100/70 dark:bg-amber-600/20 text-amber-700 dark:text-amber-300 font-semibold"
                        : "hover:bg-black/5 dark:hover:bg-white/5 text-slate-700 dark:text-slate-300"
                    }`}
                  >
                    <div className="flex items-center gap-2 truncate">
                      <Clock className="w-3.5 h-3.5 text-amber-500" />
                      <span className="truncate">Pending</span>
                    </div>
                    <span className="text-[10px] font-mono text-amber-600 dark:text-amber-400">{stats.pending}</span>
                  </button>
                </div>
              )}
            </div>

            {/* This PC Node */}
            <div className="mt-1">
              <div
                onClick={() => toggleNode("thisPc")}
                className="flex items-center gap-1.5 px-2 py-1 rounded hover:bg-black/5 dark:hover:bg-white/5 text-slate-700 dark:text-slate-300 font-semibold cursor-pointer"
              >
                {expandedNodes.thisPc ? (
                  <ChevronDown className="w-3 h-3 text-slate-400" />
                ) : (
                  <ChevronRight className="w-3 h-3 text-slate-400" />
                )}
                <Monitor className="w-3.5 h-3.5 text-blue-500" />
                <span>This PC</span>
              </div>

              {expandedNodes.thisPc && (
                <div className="ml-4 pl-2 border-l border-slate-200 dark:border-white/10 space-y-0.5 mt-0.5">
                  {/* Disk D */}
                  <div>
                    <div
                      onClick={() => toggleNode("diskD")}
                      className="flex items-center gap-1.5 px-2 py-1 rounded hover:bg-black/5 dark:hover:bg-white/5 text-slate-700 dark:text-slate-300 cursor-pointer"
                    >
                      {expandedNodes.diskD ? (
                        <ChevronDown className="w-3 h-3 text-slate-400" />
                      ) : (
                        <ChevronRight className="w-3 h-3 text-slate-400" />
                      )}
                      <HardDrive className="w-3.5 h-3.5 text-slate-500" />
                      <span className="truncate">Local Disk (D:)</span>
                    </div>

                    {expandedNodes.diskD && (
                      <div className="ml-4 pl-2 border-l border-slate-200 dark:border-white/10 space-y-0.5 mt-0.5">
                        <div
                          onClick={() => {
                            setFolderPath("D:\\OCR\\PDF\\Penn PDF");
                            void scanCurrentFolder("D:\\OCR\\PDF\\Penn PDF");
                          }}
                          className="flex items-center gap-2 px-2 py-1 rounded bg-[#E5F3FF] dark:bg-[#003774]/40 text-[#005FB8] dark:text-blue-300 font-semibold cursor-pointer"
                        >
                          <FolderOpen className="w-3.5 h-3.5 text-amber-500 fill-amber-500" />
                          <span className="truncate">Penn PDF (47)</span>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* Database Tables Node */}
            <div className="mt-1">
              <div
                onClick={() => toggleNode("dbSection")}
                className="flex items-center gap-1.5 px-2 py-1 rounded hover:bg-black/5 dark:hover:bg-white/5 text-slate-700 dark:text-slate-300 font-semibold cursor-pointer"
              >
                {expandedNodes.dbSection ? (
                  <ChevronDown className="w-3 h-3 text-slate-400" />
                ) : (
                  <ChevronRight className="w-3 h-3 text-slate-400" />
                )}
                <Database className="w-3.5 h-3.5 text-indigo-500" />
                <span>SQLite Database</span>
              </div>

              {expandedNodes.dbSection && (
                <div className="ml-4 pl-2 border-l border-slate-200 dark:border-white/10 space-y-0.5 mt-0.5">
                  <button
                    onClick={() => setActiveTab("database")}
                    className="w-full flex items-center justify-between px-2 py-1 rounded hover:bg-black/5 dark:hover:bg-white/5 text-slate-700 dark:text-slate-300 text-left"
                  >
                    <span>voters (Table)</span>
                    <span className="text-[10px] font-mono text-emerald-600 dark:text-emerald-400">Live</span>
                  </button>
                  <button
                    onClick={() => setActiveTab("database")}
                    className="w-full flex items-center justify-between px-2 py-1 rounded hover:bg-black/5 dark:hover:bg-white/5 text-slate-700 dark:text-slate-300 text-left"
                  >
                    <span>polling_stations</span>
                    <span className="text-[10px] font-mono opacity-60">Ready</span>
                  </button>
                </div>
              )}
            </div>
          </nav>

          {/* 4B. CENTER FILE EXPLORER MAIN AREA */}
          <main className="flex-1 flex flex-col min-h-0 overflow-y-auto bg-white dark:bg-[#191919]">
            {isScanning ? (
              <div className="flex-1 flex flex-col items-center justify-center gap-2 text-slate-400 p-8">
                <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
                <span className="text-xs font-semibold">Reading folder contents…</span>
              </div>
            ) : filteredItems.length === 0 ? (
              <div className="flex-1 flex flex-col items-center justify-center gap-2 text-slate-400 p-8 text-center">
                <Folder className="w-12 h-12 text-slate-300 dark:text-slate-700" />
                <div className="text-xs font-bold text-slate-700 dark:text-slate-300">
                  This folder is empty or no files match search
                </div>
                <p className="text-[11px] text-slate-500">Check the path or change filter options above</p>
              </div>
            ) : viewStyle === "details" ? (
              /* Table View */
              <div className="min-w-full inline-block align-middle">
                <table className="w-full text-left text-xs border-collapse">
                  <thead className="bg-[#F8F9FA] dark:bg-[#202020] border-b border-slate-200 dark:border-white/10 text-slate-500 dark:text-slate-400 font-medium sticky top-0 z-10 select-none">
                    <tr>
                      <th className="w-10 px-3 py-2">
                        <button onClick={toggleSelectAll}>
                          {selectedPaths.size > 0 && selectedPaths.size === filteredItems.length ? (
                            <CheckSquare className="w-3.5 h-3.5 text-blue-600" />
                          ) : selectedPaths.size > 0 ? (
                            <CheckSquare className="w-3.5 h-3.5 text-blue-600 opacity-70" />
                          ) : (
                            <Square className="w-3.5 h-3.5 text-slate-400" />
                          )}
                        </button>
                      </th>
                      <th className="px-3 py-2">Name</th>
                      <th className="px-3 py-2 w-32">Status</th>
                      <th className="px-3 py-2 w-24">Size</th>
                      <th className="px-3 py-2 w-20 text-center">Pages</th>
                      <th className="px-3 py-2 w-28 text-right">Extracted Voters</th>
                      <th className="px-3 py-2 w-28 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-white/5">
                    {filteredItems.map((item) => {
                      const isSelected = selectedItem?.stored_path === item.stored_path;
                      const isChecked = selectedPaths.has(item.stored_path);
                      const fileProgress = item.file_id ? fileJobProgress[item.file_id] : undefined;
                      const pagesDone = fileProgress ? fileProgress.pagesCompleted : (item.pages_done || 0);
                      const pagesTotal = fileProgress && fileProgress.pagesTotal > 0 ? fileProgress.pagesTotal : (item.page_count || 1);
                      const isCompleted = item.status === "completed" || (fileProgress && fileProgress.done);
                      const isCurrentlyProcessing = item.status === "processing" || (fileProgress && !fileProgress.done && isJobRunning);
                      const filePercent = isCompleted ? 100 : (pagesTotal > 0 ? Math.min(100, Math.round((pagesDone / pagesTotal) * 100)) : 0);

                      return (
                        <tr
                          key={item.stored_path}
                          onClick={() => setSelectedItem(item)}
                          onDoubleClick={() => {
                            if (isCompleted) {
                              void reprocessSingle(item);
                            } else {
                              void processSingle(item);
                            }
                          }}
                          className={`cursor-pointer transition-colors ${
                            isSelected
                              ? "bg-[#E5F3FF] dark:bg-[#003774]/35 text-slate-900 dark:text-white"
                              : "hover:bg-slate-100/60 dark:hover:bg-white/5 text-slate-800 dark:text-slate-200"
                          }`}
                        >
                          <td className="px-3 py-2" onClick={(e) => e.stopPropagation()}>
                            <button onClick={() => toggleSelect(item.stored_path)}>
                              {isChecked ? (
                                <CheckSquare className="w-3.5 h-3.5 text-blue-600" />
                              ) : (
                                <Square className="w-3.5 h-3.5 text-slate-400" />
                              )}
                            </button>
                          </td>

                          <td className="px-3 py-2">
                            <div className="flex items-center gap-2 min-w-0">
                              <FileText className="w-4 h-4 text-red-500 shrink-0" />
                              <span className="truncate font-medium">{item.name}</span>
                            </div>
                          </td>

                          <td className="px-3 py-2">
                            {isCurrentlyProcessing ? (
                              <div className="flex flex-col gap-1 min-w-[150px] max-w-[200px]">
                                <div className="flex items-center justify-between text-[11px] font-mono">
                                  <span className="font-semibold text-blue-600 dark:text-blue-400 flex items-center gap-1">
                                    <Loader2 className="w-3 h-3 animate-spin" />
                                    <span>{filePercent}%</span>
                                  </span>
                                  <span className="text-slate-500 dark:text-slate-400 text-[10px]">
                                    {pagesDone}/{pagesTotal} pgs
                                  </span>
                                </div>

                                {/* Progress Bar */}
                                <div className="w-full h-1.5 rounded-full bg-slate-200 dark:bg-white/10 overflow-hidden">
                                  <div
                                    className="h-full bg-gradient-to-r from-blue-500 to-indigo-500 rounded-full transition-all duration-300"
                                    style={{
                                      width: `${Math.max(5, filePercent)}%`,
                                    }}
                                  />
                                </div>

                                {/* Speed & ETA */}
                                <div className="flex items-center justify-between text-[9px] font-mono text-slate-400">
                                  <span>{pagesPerSec > 0 ? `${pagesPerSec.toFixed(1)} pgs/s` : "GPU active"}</span>
                                  <span className="text-blue-500 dark:text-blue-400 font-bold">
                                    ETA: {etaSeconds > 0 ? (etaSeconds > 60 ? `${Math.floor(etaSeconds / 60)}m ${etaSeconds % 60}s` : `${etaSeconds}s`) : "< 10s"}
                                  </span>
                                </div>
                              </div>
                            ) : isCompleted ? (
                              <span className="inline-flex items-center gap-1 font-semibold text-emerald-600 dark:text-emerald-400 text-[11px]">
                                <CheckCircle2 className="w-3 h-3" /> Completed
                              </span>
                            ) : pagesDone > 0 ? (
                              <div className="flex flex-col gap-1 min-w-[130px] max-w-[170px]">
                                <div className="flex items-center justify-between text-[10px] font-mono text-slate-500 dark:text-slate-400">
                                  <span>{filePercent}%</span>
                                  <span>{pagesDone}/{pagesTotal} pgs</span>
                                </div>
                                <div className="w-full h-1 rounded-full bg-slate-200 dark:bg-white/10 overflow-hidden">
                                  <div className="h-full bg-blue-500 rounded-full" style={{ width: `${Math.max(5, filePercent)}%` }} />
                                </div>
                              </div>
                            ) : (
                              <span className="inline-flex items-center gap-1 text-slate-500 dark:text-slate-400 text-[11px]">
                                <Clock className="w-3 h-3" /> Pending
                              </span>
                            )}
                          </td>

                          <td className="px-3 py-2 font-mono text-[11px] text-slate-500 dark:text-slate-400">
                            {(item.size_bytes / (1024 * 1024)).toFixed(1)} MB
                          </td>

                          <td className="px-3 py-2 text-center font-mono text-[11px] text-slate-600 dark:text-slate-300">
                            {item.page_count || 1}
                          </td>

                          <td className="px-3 py-2 text-right font-mono font-bold text-emerald-600 dark:text-emerald-400 text-[11px]">
                            {item.records_count ? `${item.records_count} voters` : "—"}
                          </td>

                          <td className="px-3 py-2 text-right" onClick={(e) => e.stopPropagation()}>
                            {isCompleted ? (
                              <button
                                onClick={() => void reprocessSingle(item)}
                                disabled={actionInProgress === item.stored_path}
                                className="px-2.5 py-1 rounded bg-slate-100 dark:bg-white/10 hover:bg-slate-200 dark:hover:bg-white/15 text-[11px] font-medium text-slate-700 dark:text-slate-300 transition-colors"
                              >
                                Re-run
                              </button>
                            ) : (
                              <button
                                onClick={() => void processSingle(item)}
                                disabled={isCurrentlyProcessing || actionInProgress === item.stored_path}
                                className="px-2.5 py-1 rounded bg-[#005FB8] hover:bg-[#004E98] text-white text-[11px] font-semibold transition-colors disabled:opacity-50"
                              >
                                {isCurrentlyProcessing ? "Running…" : "Process"}
                              </button>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              /* Tiles / Cards View */
              <div className="p-4 grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                {filteredItems.map((item) => {
                  const isSelected = selectedItem?.stored_path === item.stored_path;
                  const isChecked = selectedPaths.has(item.stored_path);
                  const fileProgress = item.file_id ? fileJobProgress[item.file_id] : undefined;
                  const pagesDone = fileProgress ? fileProgress.pagesCompleted : (item.pages_done || 0);
                  const pagesTotal = fileProgress && fileProgress.pagesTotal > 0 ? fileProgress.pagesTotal : (item.page_count || 1);
                  const isCompleted = item.status === "completed" || (fileProgress && fileProgress.done);
                  const isCurrentlyProcessing = item.status === "processing" || (fileProgress && !fileProgress.done && isJobRunning);
                  const filePercent = isCompleted ? 100 : (pagesTotal > 0 ? Math.min(100, Math.round((pagesDone / pagesTotal) * 100)) : 0);

                  return (
                    <div
                      key={item.stored_path}
                      onClick={() => setSelectedItem(item)}
                      className={`p-3 rounded-lg border flex flex-col justify-between gap-2 cursor-pointer transition-all ${
                        isSelected
                          ? "bg-[#E5F3FF] dark:bg-[#003774]/35 border-blue-400 dark:border-blue-500 shadow-2xs"
                          : "bg-white dark:bg-[#202020] border-slate-200 dark:border-white/10 hover:border-slate-300 dark:hover:border-white/20"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-center gap-2 min-w-0">
                          <FileText className="w-6 h-6 text-red-500 shrink-0" />
                          <div className="min-w-0 flex-1">
                            <h4 className="text-xs font-semibold text-slate-900 dark:text-white truncate">
                              {item.name}
                            </h4>
                            <span className="text-[10px] text-slate-500 dark:text-slate-400 font-mono">
                              {(item.size_bytes / (1024 * 1024)).toFixed(1)} MB · {item.page_count || 1} pgs
                            </span>
                          </div>
                        </div>

                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            toggleSelect(item.stored_path);
                          }}
                          className="text-slate-400"
                        >
                          {isChecked ? (
                            <CheckSquare className="w-4 h-4 text-blue-600" />
                          ) : (
                            <Square className="w-4 h-4 text-slate-400" />
                          )}
                        </button>
                      </div>

                      {isCurrentlyProcessing ? (
                        <div className="my-1.5 space-y-1">
                          <div className="flex items-center justify-between text-[10px] font-mono">
                            <span className="text-blue-600 dark:text-blue-400 font-bold">
                              {filePercent}%
                            </span>
                            <span className="text-slate-400">
                              {pagesDone}/{pagesTotal} pgs
                            </span>
                          </div>
                          <div className="w-full h-1.5 rounded-full bg-slate-200 dark:bg-white/10 overflow-hidden">
                            <div
                              className="h-full bg-gradient-to-r from-blue-500 to-indigo-500 rounded-full transition-all duration-300"
                              style={{
                                width: `${Math.max(5, filePercent)}%`,
                              }}
                            />
                          </div>
                          <div className="text-[9px] font-mono text-slate-400 flex justify-between">
                            <span>{pagesPerSec > 0 ? `${pagesPerSec.toFixed(1)} pgs/s` : "OCR active"}</span>
                            <span className="text-blue-500 font-bold">
                              ETA: {etaSeconds > 0 ? `${etaSeconds}s` : "< 10s"}
                            </span>
                          </div>
                        </div>
                      ) : pagesDone > 0 && !isCompleted ? (
                        <div className="my-1.5 space-y-1">
                          <div className="flex items-center justify-between text-[10px] font-mono text-slate-500 dark:text-slate-400">
                            <span>{filePercent}%</span>
                            <span>{pagesDone}/{pagesTotal} pgs</span>
                          </div>
                          <div className="w-full h-1 rounded-full bg-slate-200 dark:bg-white/10 overflow-hidden">
                            <div className="h-full bg-blue-500 rounded-full" style={{ width: `${Math.max(5, filePercent)}%` }} />
                          </div>
                        </div>
                      ) : null}

                      <div className="flex items-center justify-between pt-2 border-t border-slate-100 dark:border-white/5 text-[11px]">
                        {isCompleted ? (
                          <span className="text-emerald-600 dark:text-emerald-400 font-bold flex items-center gap-1">
                            <CheckCircle2 className="w-3 h-3" /> {item.records_count || 0} Voters
                          </span>
                        ) : isCurrentlyProcessing ? (
                          <span className="text-blue-600 dark:text-blue-400 font-semibold flex items-center gap-1 animate-pulse text-[11px]">
                            <Loader2 className="w-3 h-3 animate-spin" /> Processing…
                          </span>
                        ) : (
                          <span className="text-slate-400 flex items-center gap-1">
                            <Clock className="w-3 h-3" /> Pending
                          </span>
                        )}

                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            if (isCompleted) {
                              void reprocessSingle(item);
                            } else {
                              void processSingle(item);
                            }
                          }}
                          className="px-2 py-0.5 rounded bg-slate-100 dark:bg-white/10 hover:bg-blue-600 hover:text-white text-[10px] font-semibold transition-colors"
                        >
                          {isCompleted ? "Re-run" : "Run"}
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </main>

          {/* 4C. RIGHT DETAILS / PREVIEW PANE (COLLAPSIBLE) */}
          {showDetailsPane && (
            <aside className="w-72 lg:w-80 bg-[#FBFBFB] dark:bg-[#1C1C1C] border-l border-slate-200 dark:border-white/10 p-4 flex flex-col gap-4 shrink-0 text-xs overflow-y-auto">
              <div className="flex items-center justify-between border-b border-slate-200 dark:border-white/10 pb-2">
                <span className="font-bold text-slate-700 dark:text-slate-300">File Details</span>
                <button
                  onClick={() => setShowDetailsPane(false)}
                  className="text-slate-400 hover:text-slate-600"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>

              {selectedItem ? (
                <div className="space-y-4">
                  {/* File Icon & Name */}
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-red-500/10 border border-red-500/20 flex items-center justify-center">
                      <FileText className="w-6 h-6 text-red-500" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <h3 className="font-bold text-slate-900 dark:text-white truncate">
                        {selectedItem.name}
                      </h3>
                      <p className="text-[11px] text-slate-400 font-mono">
                        PDF Document ({selectedItem.page_count || 1} pages)
                      </p>
                    </div>
                  </div>

                  {/* Metadata Table */}
                  <div className="space-y-2 bg-white dark:bg-[#252525] p-3 rounded-lg border border-slate-200 dark:border-white/10 font-mono text-[11px]">
                    <div className="flex justify-between">
                      <span className="text-slate-400">File Size:</span>
                      <span className="text-slate-700 dark:text-slate-300">
                        {(selectedItem.size_bytes / (1024 * 1024)).toFixed(2)} MB
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Status:</span>
                      <span className="font-bold text-emerald-600 dark:text-emerald-400 capitalize">
                        {selectedItem.status}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Extracted Voters:</span>
                      <span className="font-bold text-blue-600 dark:text-blue-400">
                        {selectedItem.records_count || liveExtractedElectors.length || 0}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Folder:</span>
                      <span className="text-slate-700 dark:text-slate-300 truncate max-w-[140px]">
                        {selectedItem.folder_name}
                      </span>
                    </div>

                    {/* In-Flight Live Progress & ETA */}
                    {(() => {
                      const selProgress = selectedItem.file_id ? fileJobProgress[selectedItem.file_id] : undefined;
                      const selDone = selProgress ? selProgress.pagesCompleted : (selectedItem.pages_done || 0);
                      const selTotal = selProgress && selProgress.pagesTotal > 0 ? selProgress.pagesTotal : (selectedItem.page_count || 1);
                      const selPercent = selectedItem.status === "completed" ? 100 : (selTotal > 0 ? Math.min(100, Math.round((selDone / selTotal) * 100)) : 0);
                      const isProc = selectedItem.status === "processing" || (selProgress && !selProgress.done && isJobRunning);

                      if (isProc || (selDone > 0 && selectedItem.status !== "completed")) {
                        return (
                          <div className="pt-2 border-t border-slate-200 dark:border-white/10 space-y-1.5">
                            <div className="flex items-center justify-between text-[11px]">
                              <span className="text-blue-600 dark:text-blue-400 font-bold flex items-center gap-1">
                                {isProc ? <Loader2 className="w-3 h-3 animate-spin" /> : null}
                                <span>{isProc ? "In Progress" : "Progress"}</span>
                              </span>
                              <span className="text-slate-700 dark:text-slate-300 font-bold">
                                {selPercent}% ({selDone}/{selTotal} pgs)
                              </span>
                            </div>
                            <div className="w-full h-2 rounded-full bg-slate-100 dark:bg-white/10 overflow-hidden">
                              <div
                                className="h-full bg-gradient-to-r from-blue-500 to-indigo-500 rounded-full transition-all duration-300"
                                style={{ width: `${Math.max(5, selPercent)}%` }}
                              />
                            </div>
                            {isProc && (
                              <div className="flex justify-between text-[10px] text-slate-400">
                                <span>{pagesPerSec > 0 ? `${pagesPerSec.toFixed(1)} pgs/sec` : "GPU active"}</span>
                                <span className="text-blue-500 font-bold">
                                  ETA: {etaSeconds > 0 ? (etaSeconds > 60 ? `${Math.floor(etaSeconds / 60)}m ${etaSeconds % 60}s` : `${etaSeconds}s`) : "< 10s"}
                                </span>
                              </div>
                            )}
                          </div>
                        );
                      }
                      return null;
                    })()}
                  </div>

                  {/* Action Buttons */}
                  <div className="space-y-2">
                    {selectedItem.status === "completed" ? (
                      <button
                        onClick={() => void reprocessSingle(selectedItem)}
                        disabled={actionInProgress === selectedItem.stored_path}
                        className="w-full py-2 rounded bg-slate-200 dark:bg-white/10 hover:bg-slate-300 dark:hover:bg-white/15 font-semibold text-slate-800 dark:text-slate-200 flex items-center justify-center gap-1.5 transition-colors"
                      >
                        <RotateCcw className="w-3.5 h-3.5" />
                        <span>Re-Process Document</span>
                      </button>
                    ) : (
                      <button
                        onClick={() => void processSingle(selectedItem)}
                        disabled={
                          selectedItem.status === "processing" ||
                          actionInProgress === selectedItem.stored_path
                        }
                        className="w-full py-2 rounded bg-[#005FB8] hover:bg-[#004E98] font-semibold text-white flex items-center justify-center gap-1.5 transition-colors shadow-xs"
                      >
                        <Zap className="w-3.5 h-3.5 fill-white" />
                        <span>Process This Document</span>
                      </button>
                    )}

                    <button
                      onClick={() => setActiveTab("database")}
                      className="w-full py-2 rounded border border-slate-300 dark:border-white/10 hover:bg-slate-100 dark:hover:bg-white/5 font-semibold text-slate-700 dark:text-slate-300 flex items-center justify-center gap-1.5 transition-colors"
                    >
                      <Database className="w-3.5 h-3.5 text-slate-500" />
                      <span>View in Database Explorer</span>
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center h-48 text-center text-slate-400">
                  <Info className="w-8 h-8 opacity-40 mb-2" />
                  <span>Select a file to view details</span>
                </div>
              )}
            </aside>
          )}
        </div>
      ) : activeTab === "database" ? (
        /* Database Records Tab */
        <div className="flex-1 flex flex-col min-h-0 overflow-hidden bg-white dark:bg-[#191919]">
          <DatabasePage />
        </div>
      ) : (
        /* Local Deployment Tab */
        <div className="flex-1 flex flex-col min-h-0 overflow-hidden bg-white dark:bg-[#191919]">
          <LocalDeploymentPage />
        </div>
      )}

      {/* ========================================================================= */}
      {/* 5. WINDOWS 11 STATUS BAR (BOTTOM) */}
      {/* ========================================================================= */}
      <div className="h-6 px-3 bg-[#EAEAEA] dark:bg-[#181818] border-t border-slate-300 dark:border-white/10 flex items-center justify-between text-[11px] text-slate-600 dark:text-slate-400 shrink-0 font-mono">
        <div className="flex items-center gap-4">
          <span>{filteredItems.length} items</span>
          {selectedPaths.size > 0 && (
            <span className="text-blue-600 dark:text-blue-400 font-semibold">
              {selectedPaths.size} item(s) selected
            </span>
          )}
        </div>

        <div className="flex items-center gap-4">
          {isJobRunning && (
            <span className="flex items-center gap-1.5 text-blue-600 dark:text-blue-400 font-bold">
              <Loader2 className="w-3 h-3 animate-spin" />
              <span>
                Running: {activeJobProgress.toFixed(0)}% ({pagesPerSec.toFixed(1)} pgs/sec)
              </span>
            </span>
          )}

          <button
            onClick={toggleAutoInsertToDb}
            className={`hover:underline ${
              autoInsertToDb
                ? "text-emerald-600 dark:text-emerald-400 font-bold"
                : "text-slate-400"
            }`}
            title="Toggle Automatic SQLite Database Promotion"
          >
            Auto-DB: {autoInsertToDb ? "ON" : "OFF"}
          </button>

          <span>PaddleOCR PP-OCRv5 (GPU:0)</span>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* 6. WINDOWS 11 FLOATING OPERATION PROGRESS BOX (NATIVE STYLE) */}
      {/* ========================================================================= */}
      {isJobRunning && (
        <div className="fixed bottom-10 right-6 w-96 bg-white dark:bg-[#252525] rounded-xl shadow-2xl border border-slate-300 dark:border-white/15 overflow-hidden z-50 animate-in slide-in-from-bottom-5 duration-200">
          {/* Header */}
          <div className="px-3.5 py-2.5 bg-[#F3F3F3] dark:bg-[#1E1E1E] border-b border-slate-200 dark:border-white/10 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Loader2 className="w-4 h-4 text-[#005FB8] dark:text-blue-400 animate-spin" />
              <span className="font-bold text-xs text-slate-800 dark:text-white">
                Processing Electoral Rolls
              </span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-mono font-bold text-[#005FB8] dark:text-blue-400">
                {activeJobProgress.toFixed(0)}%
              </span>
              <button
                onClick={() => void cancelActiveJob()}
                className="w-6 h-6 rounded hover:bg-red-500 hover:text-white flex items-center justify-center text-slate-400 transition-colors"
                title="Cancel Operation"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          {/* Body */}
          <div className="p-4 space-y-3">
            {/* Progress Bar */}
            <div className="space-y-1">
              <div className="w-full h-2.5 rounded-full bg-slate-100 dark:bg-white/10 overflow-hidden relative">
                <div
                  className="h-full bg-gradient-to-r from-[#005FB8] to-blue-400 rounded-full transition-all duration-300 shadow-xs"
                  style={{ width: `${Math.max(4, activeJobProgress)}%` }}
                />
              </div>
            </div>

            {/* Metrics */}
            <div className="space-y-1.5 font-mono text-[11px] text-slate-600 dark:text-slate-300">
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Time remaining:</span>
                <span className="font-bold text-blue-600 dark:text-blue-400">
                  {etaSeconds > 0
                    ? etaSeconds > 60
                      ? `About ${Math.floor(etaSeconds / 60)} min ${etaSeconds % 60} sec`
                      : `About ${etaSeconds} seconds`
                    : "Calculating…"}
                </span>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-slate-400">Processing speed:</span>
                <span className="font-semibold text-slate-800 dark:text-slate-200">
                  {pagesPerSec > 0 ? `${pagesPerSec.toFixed(1)} Pages/sec` : "GPU Warming up"}
                </span>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-slate-400">Database ingestion:</span>
                <span className="text-emerald-600 dark:text-emerald-400 font-bold">
                  {autoInsertToDb ? "Auto-Insert ON" : "Manual"}
                </span>
              </div>
            </div>

            {/* Footer Actions */}
            <div className="pt-2 border-t border-slate-100 dark:border-white/5 flex justify-end">
              <button
                onClick={() => void cancelActiveJob()}
                className="px-3 py-1 rounded bg-slate-100 dark:bg-white/10 hover:bg-red-600 hover:text-white text-xs font-semibold text-slate-700 dark:text-slate-300 transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

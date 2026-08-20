"use client";

import React, { useEffect, useState, useMemo } from "react";
import { useSerenaStore } from "@/store/useSerenaStore";
import { SerenaHeader } from "@/components/SerenaHeader";
import { SerenaMetricsHud } from "@/components/SerenaMetricsHud";
import { SerenaToolbar } from "@/components/SerenaToolbar";
import { SerenaPdfCard } from "@/components/SerenaPdfCard";
import { SerenaPdfTable } from "@/components/SerenaPdfTable";
import { DatabasePage } from "@/components/DatabasePage";
import { SerenaAuthModal } from "@/components/SerenaAuthBar";
import { Folder, Loader2, RefreshCw } from "lucide-react";

export default function SerenaHome() {
  const {
    checkAuth,
    loadDbFiles,
    scanCurrentFolder,
    scannedData,
    isScanning,
    searchQuery,
    statusFilter,
    sortBy,
    sortDesc,
    viewMode,
    activeTab,
    setTheme,
  } = useSerenaStore();

  const [isAuthOpen, setIsAuthOpen] = useState(false);

  // Initialize on mount: check saved theme, auth, and scan folder
  useEffect(() => {
    if (typeof window !== "undefined") {
      const savedTheme = (localStorage.getItem("serena-theme") as "dark" | "light") || "dark";
      setTheme(savedTheme);
    }
    void checkAuth();
    void loadDbFiles();
    void scanCurrentFolder();
  }, []);

  // Listen for 401 events to prompt login
  useEffect(() => {
    const handleUnauthorized = () => setIsAuthOpen(true);
    window.addEventListener("serena:unauthorized", handleUnauthorized);
    return () => window.removeEventListener("serena:unauthorized", handleUnauthorized);
  }, []);

  // Filter & Sort Scanned Items
  const filteredItems = useMemo(() => {
    if (!scannedData?.items) return [];
    return scannedData.items
      .filter((item) => {
        // Query search
        if (searchQuery.trim()) {
          const q = searchQuery.toLowerCase();
          const matchesName = item.name.toLowerCase().includes(q);
          const matchesFolder = item.folder_name.toLowerCase().includes(q);
          if (!matchesName && !matchesFolder) return false;
        }

        // Status Filter
        if (statusFilter === "all") return true;
        if (statusFilter === "pending")
          return item.status === "pending" || item.status === "unregistered";
        if (statusFilter === "completed") return item.status === "completed";
        if (statusFilter === "processing") return item.status === "processing";
        if (statusFilter === "error") return item.status === "error";
        return true;
      })
      .sort((a, b) => {
        let diff = 0;
        if (sortBy === "name") diff = a.name.localeCompare(b.name, undefined, { numeric: true });
        else if (sortBy === "size") diff = a.size_bytes - b.size_bytes;
        else if (sortBy === "pages") diff = a.page_count - b.page_count;
        else if (sortBy === "records") diff = a.records_count - b.records_count;
        else if (sortBy === "status") diff = a.status.localeCompare(b.status);
        return sortDesc ? -diff : diff;
      });
  }, [scannedData, searchQuery, statusFilter, sortBy, sortDesc]);

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-slate-50 dark:bg-obsidian-950 text-slate-900 dark:text-slate-100 min-w-0 transition-colors duration-200">
      {/* Top Header */}
      <SerenaHeader onOpenAuth={() => setIsAuthOpen(true)} />

      {/* RENDER VIEW: Batch OCR Workstation vs. Database Explorer */}
      {activeTab === "workstation" ? (
        <>
          {/* Metrics HUD */}
          <SerenaMetricsHud />

          {/* Main Workstation Deck */}
          <main className="flex-1 flex flex-col overflow-hidden p-6 gap-4 min-h-0">
            {/* Toolbar */}
            <SerenaToolbar totalFiltered={filteredItems.length} />

            {/* PDF Documents Content */}
            {isScanning ? (
              <div className="flex-1 flex flex-col items-center justify-center gap-3 text-slate-400">
                <Loader2 className="w-9 h-9 animate-spin text-serena-indigo" />
                <p className="text-sm font-semibold text-slate-700 dark:text-slate-300">
                  Scanning local folder for PDF documents…
                </p>
              </div>
            ) : filteredItems.length === 0 ? (
              <div className="flex-1 flex flex-col items-center justify-center gap-3 serena-glass rounded-3xl p-8 text-center border border-slate-200 dark:border-white/5">
                <Folder className="w-12 h-12 text-slate-400 dark:text-slate-600" />
                <div>
                  <h3 className="text-sm font-bold text-slate-700 dark:text-slate-300">No PDF files match your filter</h3>
                  <p className="text-xs text-slate-500 mt-1">
                    Try selecting a different directory or adjusting your search filters
                  </p>
                </div>
                <button
                  onClick={() => void scanCurrentFolder()}
                  className="px-4 py-2 rounded-xl bg-slate-100 dark:bg-obsidian-850 hover:bg-slate-200 dark:hover:bg-obsidian-800 border border-slate-200 dark:border-white/10 text-xs font-semibold text-slate-700 dark:text-slate-200 transition-colors flex items-center gap-1.5"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                  <span>Rescan Directory</span>
                </button>
              </div>
            ) : viewMode === "grid" ? (
              /* Cards Grid */
              <div className="flex-1 overflow-y-auto min-h-0 pr-1">
                <div className="grid grid-cols-1 md:grid-cols-2 2xl:grid-cols-3 gap-4">
                  {filteredItems.map((item) => (
                    <SerenaPdfCard key={item.stored_path} item={item} />
                  ))}
                </div>
              </div>
            ) : (
              /* High-Density Table */
              <SerenaPdfTable items={filteredItems} />
            )}
          </main>
        </>
      ) : (
        /* Database Page */
        <DatabasePage />
      )}

      {/* Auth Modal */}
      <SerenaAuthModal isOpen={isAuthOpen} onClose={() => setIsAuthOpen(false)} />
    </div>
  );
}

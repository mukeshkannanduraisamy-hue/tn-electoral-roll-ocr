"use client";

import React, { useEffect, useState, useMemo } from "react";
import { useSerenaStore } from "@/store/useSerenaStore";
import { SerenaHeader } from "@/components/SerenaHeader";
import { SerenaMetricsHud } from "@/components/SerenaMetricsHud";
import { SerenaToolbar } from "@/components/SerenaToolbar";
import { SerenaPdfCard } from "@/components/SerenaPdfCard";
import { SerenaPdfTable } from "@/components/SerenaPdfTable";
import { DatabasePage } from "@/components/DatabasePage";
import { LocalDeploymentPage } from "@/components/LocalDeploymentPage";
import { QuantumStudio } from "@/components/QuantumStudio";
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

      {/* RENDER VIEW: Quantum Studio vs. Database Explorer vs. Local Deployment */}
      {activeTab === "workstation" ? (
        <QuantumStudio />
      ) : activeTab === "database" ? (
        /* Database Page */
        <DatabasePage />
      ) : (
        /* Local Auto Deployment Page */
        <LocalDeploymentPage />
      )}

      {/* Auth Modal */}
      <SerenaAuthModal isOpen={isAuthOpen} onClose={() => setIsAuthOpen(false)} />
    </div>
  );
}

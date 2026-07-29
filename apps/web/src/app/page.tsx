"use client";

import React, { useEffect, useState } from "react";
import { useOcrStore } from "@/store/useOcrStore";
import { Navbar } from "@/components/Navbar";
import { Sidebar } from "@/components/Sidebar";
import { DocumentView } from "@/components/DocumentView";
import { PageView } from "@/components/PageView";
import { ReviewQueue } from "@/components/ReviewQueue";
import { ExportModal } from "@/components/ExportModal";
import { UploadModal } from "@/components/UploadModal";
import { BulkExtractModal } from "@/components/BulkExtractModal";
import { ShortcutsModal } from "@/components/ShortcutsModal";
import { CommandPalette } from "@/components/CommandPalette";
import { Toaster } from "sonner";
import { Loader2, X, PanelLeft } from "lucide-react";
import { VotersView } from "@/components/VotersView";
import { LoginScreen } from "@/components/LoginScreen";
import { useAuthStore } from "@/store/useAuthStore";
import { setUnauthorizedHandler } from "@/lib/voterApi";
import { DashboardView } from "@/components/DashboardView";
import { SettingsView } from "@/components/SettingsView";
import { AnalyticsView } from "@/components/AnalyticsView";
import { PollingStationsView } from "@/components/PollingStationsView";
import { ConfirmationModal } from "@/components/ConfirmationModal";

export default function Home() {
  const { loadFiles, activeTab, setActiveTab, setIsShortcutsOpen, isShortcutsOpen } = useOcrStore();

  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [isExportOpen, setIsExportOpen] = useState(false);
  const [isBulkExtractOpen, setIsBulkExtractOpen] = useState(false);
  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);

  const { user, authEnabled, checked, check, handleUnauthorized } = useAuthStore();
  const signedIn = !authEnabled || user !== null;

  useEffect(() => {
    setUnauthorizedHandler(handleUnauthorized);
    return () => setUnauthorizedHandler(null);
  }, [handleUnauthorized]);

  useEffect(() => {
    void check();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (signedIn) loadFiles();
  }, [signedIn]); // eslint-disable-line react-hooks/exhaustive-deps

  // Global keydown listeners (?, 1-7, Ctrl+K, Esc)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT")) return;

      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setIsCommandPaletteOpen((prev) => !prev);
      } else if (e.key === "?") {
        e.preventDefault();
        setIsShortcutsOpen(!isShortcutsOpen);
      } else if (e.key === "1") setActiveTab("dashboard");
      else if (e.key === "2") setActiveTab("voters");
      else if (e.key === "3") setActiveTab("polling_stations");
      else if (e.key === "4") setActiveTab("table");
      else if (e.key === "5") setActiveTab("analytics");
      else if (e.key === "6") setActiveTab("review");
      else if (e.key === "7") setActiveTab("settings");
      else if (e.key === "Escape") {
        setIsShortcutsOpen(false);
        setIsCommandPaletteOpen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isShortcutsOpen]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!checked) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-white font-bold shadow-lg shadow-indigo-500/30 animate-pulse">
            VI
          </div>
          <Loader2 className="h-5 w-5 animate-spin text-primary" />
        </div>
      </div>
    );
  }

  if (!signedIn) {
    return (
      <>
        <Toaster position="top-right" richColors />
        <LoginScreen />
      </>
    );
  }

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-background text-foreground transition-colors duration-150">
      <Toaster position="top-right" richColors />

      {/* Sticky Glass Top Navbar */}
      <Navbar
        onOpenUpload={() => setIsUploadOpen(true)}
        onOpenExport={() => setIsExportOpen(true)}
        onOpenBulkExtract={() => setIsBulkExtractOpen(true)}
        onOpenCommandPalette={() => setIsCommandPaletteOpen(true)}
      />

      {/* Main Multi-Panel Workspace */}
      <div className="flex-1 flex overflow-hidden relative">
        <Sidebar
          isOpen={isSidebarOpen}
          onClose={() => setIsSidebarOpen(false)}
          isCollapsed={isSidebarCollapsed}
          onToggleCollapse={() => setIsSidebarCollapsed((v) => !v)}
        />

        {/* Mobile backdrop */}
        {isSidebarOpen && (
          <div
            className="fixed inset-0 top-14 z-30 bg-slate-950/60 backdrop-blur-xs lg:hidden"
            onClick={() => setIsSidebarOpen(false)}
            aria-hidden="true"
          />
        )}

        {/* Mobile drawer toggle */}
        <button
          onClick={() => setIsSidebarOpen((v) => !v)}
          className="lg:hidden fixed bottom-5 left-5 z-50 h-12 w-12 rounded-full bg-primary hover:bg-primary/90 text-primary-foreground shadow-lg shadow-primary/30 flex items-center justify-center transition-colors"
          aria-label={isSidebarOpen ? "Close navigation" : "Open navigation"}
        >
          {isSidebarOpen ? <X className="w-5 h-5" /> : <PanelLeft className="w-5 h-5" />}
        </button>

        {/* Main View Router */}
        <main className="flex-1 flex overflow-hidden min-w-0">
          {activeTab === "dashboard"        && <DashboardView />}
          {activeTab === "voters"           && <VotersView />}
          {activeTab === "polling_stations" && <PollingStationsView />}
          {activeTab === "table"            && <DocumentView />}
          {activeTab === "analytics"        && <AnalyticsView />}
          {activeTab === "page"             && <PageView />}
          {activeTab === "review"           && <ReviewQueue />}
          {activeTab === "settings"         && <SettingsView />}
        </main>
      </div>

      {/* Modals & Command Palette */}
      <CommandPalette
        isOpen={isCommandPaletteOpen}
        onClose={() => setIsCommandPaletteOpen(false)}
        onOpenUpload={() => setIsUploadOpen(true)}
        onOpenExport={() => setIsExportOpen(true)}
        onOpenBulkExtract={() => setIsBulkExtractOpen(true)}
      />
      <UploadModal isOpen={isUploadOpen} onClose={() => setIsUploadOpen(false)} />
      <ExportModal isOpen={isExportOpen} onClose={() => setIsExportOpen(false)} />
      <BulkExtractModal isOpen={isBulkExtractOpen} onClose={() => setIsBulkExtractOpen(false)} />
      <ShortcutsModal />
      <ConfirmationModal />
    </div>
  );
}

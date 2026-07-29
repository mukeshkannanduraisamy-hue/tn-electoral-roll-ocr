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
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

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

  // Global keydown: ?, 1-7, Esc
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT")) return;

      if (e.key === "?") {
        e.preventDefault();
        setIsShortcutsOpen(!isShortcutsOpen);
      } else if (e.key === "1") setActiveTab("dashboard");
      else if (e.key === "2") setActiveTab("voters");
      else if (e.key === "3") setActiveTab("table");
      else if (e.key === "4") setActiveTab("analytics");
      else if (e.key === "5") setActiveTab("page");
      else if (e.key === "6") setActiveTab("review");
      else if (e.key === "7") setActiveTab("settings");
      else if (e.key === "Escape") setIsShortcutsOpen(false);
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isShortcutsOpen]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!checked) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[hsl(var(--background))]">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center">
            <svg className="w-4 h-4 text-white animate-pulse" viewBox="0 0 24 24" fill="currentColor">
              <path d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
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
    <div className="flex flex-col h-screen overflow-hidden bg-[hsl(var(--background))] text-foreground transition-colors duration-200">
      <Toaster position="top-right" richColors />

      {/* Top Navbar */}
      <Navbar
        onOpenUpload={() => setIsUploadOpen(true)}
        onOpenExport={() => setIsExportOpen(true)}
        onOpenBulkExtract={() => setIsBulkExtractOpen(true)}
      />

      {/* Main Workspace */}
      <div className="flex-1 flex overflow-hidden relative">
        <Sidebar isOpen={isSidebarOpen} onClose={() => setIsSidebarOpen(false)} />

        {/* Mobile backdrop */}
        {isSidebarOpen && (
          <div
            className="fixed inset-0 top-14 z-30 bg-slate-900/60 backdrop-blur-sm lg:hidden"
            onClick={() => setIsSidebarOpen(false)}
            aria-hidden="true"
          />
        )}

        {/* Mobile drawer toggle */}
        <button
          onClick={() => setIsSidebarOpen((v) => !v)}
          className="lg:hidden fixed bottom-5 left-5 z-50 h-12 w-12 rounded-full bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-600/30 flex items-center justify-center transition-colors"
          aria-label={isSidebarOpen ? "Close navigation" : "Open navigation"}
        >
          {isSidebarOpen ? <X className="w-5 h-5" /> : <PanelLeft className="w-5 h-5" />}
        </button>

        {/* Main content area */}
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

      {/* Modals */}
      <UploadModal isOpen={isUploadOpen} onClose={() => setIsUploadOpen(false)} />
      <ExportModal isOpen={isExportOpen} onClose={() => setIsExportOpen(false)} />
      <BulkExtractModal isOpen={isBulkExtractOpen} onClose={() => setIsBulkExtractOpen(false)} />
      <ShortcutsModal />
      <ConfirmationModal />
    </div>
  );
}

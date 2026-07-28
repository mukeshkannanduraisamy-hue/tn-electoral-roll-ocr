"use client";

import React, { useEffect, useState } from "react";
import { useOcrStore } from "@/store/useOcrStore";
import { Navbar } from "@/components/Navbar";
import { Sidebar } from "@/components/Sidebar";
import { TableView } from "@/components/TableView";
import { PageView } from "@/components/PageView";
import { ReviewQueue } from "@/components/ReviewQueue";
import { ExportModal } from "@/components/ExportModal";
import { UploadModal } from "@/components/UploadModal";
import { BulkExtractModal } from "@/components/BulkExtractModal";
import { ShortcutsModal } from "@/components/ShortcutsModal";
import { Toaster } from "sonner";
import { Loader2, PanelLeft, X } from "lucide-react";
import { VotersView } from "@/components/VotersView";
import { LoginScreen } from "@/components/LoginScreen";
import { useAuthStore } from "@/store/useAuthStore";
import { setUnauthorizedHandler } from "@/lib/voterApi";

export default function Home() {
  const { loadFiles, activeTab, setActiveTab, setIsShortcutsOpen, isShortcutsOpen } = useOcrStore();

  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [isExportOpen, setIsExportOpen] = useState(false);
  const [isBulkExtractOpen, setIsBulkExtractOpen] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  const { user, authEnabled, checked, check, handleUnauthorized } = useAuthStore();
  const signedIn = !authEnabled || user !== null;

  // Any API call that 401s routes through here, so a session that expires
  // mid-session drops straight back to the login screen instead of leaving
  // the UI silently failing every request.
  useEffect(() => {
    setUnauthorizedHandler(handleUnauthorized);
    return () => setUnauthorizedHandler(null);
  }, [handleUnauthorized]);

  useEffect(() => {
    void check();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Load workspace data only once there is a session; firing these while
  // signed out would just produce a burst of 401s.
  useEffect(() => {
    if (signedIn) loadFiles();
  }, [signedIn]); // eslint-disable-line react-hooks/exhaustive-deps

  // Global keydown listeners for ?, 1, 2, 3, Esc
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT")) {
        return;
      }

      if (e.key === "?") {
        e.preventDefault();
        setIsShortcutsOpen(!isShortcutsOpen);
      } else if (e.key === "1") {
        setActiveTab("table");
      } else if (e.key === "2") {
        setActiveTab("page");
      } else if (e.key === "3") {
        setActiveTab("review");
      } else if (e.key === "Escape") {
        setIsShortcutsOpen(false);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isShortcutsOpen]); // eslint-disable-line react-hooks/exhaustive-deps

  // Hold the splash until the session check resolves. Rendering the login
  // form first would flash it at an already-signed-in user on every reload.
  if (!checked) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950">
        <Loader2 className="h-6 w-6 animate-spin text-indigo-500" />
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
    <div className="flex flex-col h-screen overflow-hidden bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 transition-colors duration-200">
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

        {/* Backdrop for the mobile drawer */}
        {isSidebarOpen && (
          <div
            className="fixed inset-0 top-16 z-30 bg-slate-900/50 backdrop-blur-sm lg:hidden"
            onClick={() => setIsSidebarOpen(false)}
            aria-hidden="true"
          />
        )}

        {/* Drawer toggle -- only exists on narrow screens */}
        <button
          onClick={() => setIsSidebarOpen((v) => !v)}
          className="lg:hidden fixed bottom-5 left-5 z-50 h-12 w-12 rounded-full bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-600/30 flex items-center justify-center transition-colors"
          aria-label={isSidebarOpen ? "Close document list" : "Open document list"}
          aria-expanded={isSidebarOpen}
        >
          {isSidebarOpen ? <X className="w-5 h-5" /> : <PanelLeft className="w-5 h-5" />}
        </button>

        <main className="flex-1 flex overflow-hidden min-w-0">
          {activeTab === "table" && <TableView />}
          {activeTab === "page" && <PageView />}
          {activeTab === "review" && <ReviewQueue />}
          {activeTab === "voters" && <VotersView />}
        </main>
      </div>

      {/* Modals */}
      <UploadModal isOpen={isUploadOpen} onClose={() => setIsUploadOpen(false)} />
      <ExportModal isOpen={isExportOpen} onClose={() => setIsExportOpen(false)} />
      <BulkExtractModal
        isOpen={isBulkExtractOpen}
        onClose={() => setIsBulkExtractOpen(false)}
      />
      <ShortcutsModal />
    </div>
  );
}

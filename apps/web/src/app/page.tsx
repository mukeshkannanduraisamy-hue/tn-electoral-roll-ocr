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

export default function Home() {
  const { loadFiles, activeTab, setActiveTab, setIsShortcutsOpen, isShortcutsOpen } = useOcrStore();

  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [isExportOpen, setIsExportOpen] = useState(false);
  const [isBulkExtractOpen, setIsBulkExtractOpen] = useState(false);

  useEffect(() => {
    loadFiles();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

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
      <div className="flex-1 flex overflow-hidden">
        <Sidebar />

        <main className="flex-1 flex overflow-hidden">
          {activeTab === "table" && <TableView />}
          {activeTab === "page" && <PageView />}
          {activeTab === "review" && <ReviewQueue />}
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

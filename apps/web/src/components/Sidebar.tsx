"use client";

import React, { useEffect, useState } from "react";
import {
  FileText,
  Trash2,
  CheckCircle,
  AlertCircle,
  Clock,
  Loader2,
  RefreshCw,
} from "lucide-react";
import { useOcrStore } from "@/store/useOcrStore";
import { fetchFilePages } from "@/lib/api";

interface SidebarProps {
  /** Drawer visibility below the `lg` breakpoint. Ignored on wide screens. */
  isOpen?: boolean;
  onClose?: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ isOpen = false, onClose }) => {
  const {
    files,
    activeFileId,
    setActiveFileId,
    activePageId,
    setActivePageId,
    deleteFile,
    fileJobProgress,
    pageRefreshing,
    reocrSinglePage,
  } = useOcrStore();

  const [pagesIndex, setPagesIndex] = useState<any[]>([]);
  const [isLoadingPages, setIsLoadingPages] = useState(false);

  const activeFile = files.find((f) => f.id === activeFileId);

  useEffect(() => {
    if (!activeFileId) {
      setPagesIndex([]);
      return;
    }
    setIsLoadingPages(true);
    fetchFilePages(activeFileId)
      .then((pages) => {
        setPagesIndex(pages);
        if (pages.length > 0) {
          setActivePageId(pages[0].id);
        } else {
          setActivePageId(null);
        }
      })
      .catch((err) => console.error(err))
      .finally(() => setIsLoadingPages(false));
  }, [activeFileId]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleRefreshPageClick = async (e: React.MouseEvent, pageId: string) => {
    e.stopPropagation();
    const updated = await reocrSinglePage(pageId);
    if (updated && activeFileId) {
      fetchFilePages(activeFileId).then((pages) => setPagesIndex(pages));
    }
  };

  const getStatusIcon = (status: string, fileId: string) => {
    const progress = fileJobProgress[fileId];
    if (progress && !progress.done) {
      return <Loader2 className="w-3.5 h-3.5 text-indigo-500 animate-spin" />;
    }
    switch (status) {
      case "completed":
        return <CheckCircle className="w-3.5 h-3.5 text-emerald-500" />;
      case "error":
        return <AlertCircle className="w-3.5 h-3.5 text-rose-500" />;
      case "processing":
        return <Loader2 className="w-3.5 h-3.5 text-indigo-500 animate-spin" />;
      default:
        return <Clock className="w-3.5 h-3.5 text-slate-400" />;
    }
  };

  return (
    // Below `lg` the sidebar is an overlay drawer: at 375px a fixed 16rem
    // column left the table roughly 110px wide, which is unusable. On wide
    // screens it stays an ordinary inline column.
    //
    // The slide uses a data attribute + plain CSS rather than conditional
    // `translate-x-*` utilities. Toggling between two same-specificity
    // Tailwind translate classes leaves the resolved transform dependent on
    // stylesheet order, which is not something the markup should have to
    // reason about. See `globals.css` -> [data-drawer].
    <aside
      data-drawer={isOpen ? "open" : "closed"}
      className="
        w-64 shrink-0 border-r border-slate-200 dark:border-slate-800/80
        bg-slate-50/95 dark:bg-slate-950/95 lg:bg-slate-50/50 lg:dark:bg-slate-950
        backdrop-blur lg:backdrop-blur-none
        flex flex-col h-[calc(100vh-4rem)] select-none
        fixed lg:static top-16 lg:top-auto left-0 z-40
      "
    >
      {/* Files List Header */}
      <div className="px-4 py-3 text-[11px] font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider flex items-center justify-between border-b border-slate-200 dark:border-slate-800">
        <span>Document List ({files.length})</span>
        <span className="text-[10px] text-slate-400 dark:text-slate-600">Corpus</span>
      </div>

      {/* Files List */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1.5 min-h-0">
        {files.length === 0 && (
          <div className="text-center py-12 px-4 text-slate-400 dark:text-slate-500 text-xs leading-relaxed">
            No PDF files imported.<br />Click <strong className="text-indigo-600 dark:text-indigo-400">Upload PDF</strong> to start.
          </div>
        )}

        {files.map((file) => {
          const isActive = file.id === activeFileId;
          const progress = fileJobProgress[file.id];
          const pct = progress
            ? progress.pagesTotal > 0
              ? ((progress.pagesCompleted + progress.pagesFailed) / progress.pagesTotal) * 100
              : 0
            : 0;

          return (
            <div key={file.id} className="group relative">
              <button
                onClick={() => {
                  setActiveFileId(file.id);
                  // On mobile the drawer covers the content it just loaded.
                  onClose?.();
                }}
                className={`w-full text-left p-3 rounded-xl border transition-all flex items-start gap-3 ${
                  isActive
                    ? "bg-white dark:bg-slate-900 border-indigo-500/50 dark:border-indigo-500/50 text-slate-900 dark:text-slate-100 shadow-sm"
                    : "bg-white/40 dark:bg-slate-900/30 border-slate-200/60 dark:border-slate-800/60 text-slate-600 dark:text-slate-400 hover:bg-white dark:hover:bg-slate-900 hover:text-slate-900 dark:hover:text-slate-200"
                }`}
              >
                <FileText className={`w-4 h-4 mt-0.5 flex-shrink-0 ${isActive ? "text-indigo-600 dark:text-indigo-400" : "text-slate-400"}`} />
                <div className="flex-1 min-w-0 pr-4">
                  <div className="text-xs font-semibold truncate">{file.name}</div>
                  <div className="flex items-center gap-1.5 text-[10px] text-slate-400 mt-1">
                    <span>{file.page_count || "?"} pg</span>
                    <span>·</span>
                    {getStatusIcon(file.status, file.id)}
                    <span className="capitalize font-medium">{file.status}</span>
                  </div>

                  {progress && !progress.done && (
                    <div className="mt-2 w-full h-1.5 rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden">
                      <div
                        className="h-full bg-indigo-600 dark:bg-indigo-500 transition-all duration-200"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  )}
                </div>
              </button>

              <button
                onClick={(e) => {
                  e.stopPropagation();
                  deleteFile(file.id);
                }}
                className="absolute right-2 top-3 opacity-0 group-hover:opacity-100 p-1 text-slate-400 hover:text-rose-600 dark:hover:text-rose-400 transition-all rounded"
                title="Delete document"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          );
        })}
      </div>

      {/* Pages List for Selected File */}
      {activeFile && (
        <div className="border-t border-slate-200 dark:border-slate-800 bg-white/50 dark:bg-slate-900/30 flex flex-col" style={{ maxHeight: "45%" }}>
          <div className="px-4 py-2.5 border-b border-slate-200 dark:border-slate-800 text-[11px] font-bold text-slate-500 dark:text-slate-400 flex items-center justify-between shrink-0">
            <span className="truncate pr-2">Pages in {activeFile.name}</span>
            {isLoadingPages ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin text-indigo-500" />
            ) : (
              <span className="text-slate-400 font-medium">{pagesIndex.length} pg</span>
            )}
          </div>

          <div className="overflow-y-auto flex-1 p-2 space-y-1">
            {pagesIndex.map((p) => {
              const isPageActive = p.id === activePageId;
              const isRefreshing = pageRefreshing[p.id];
              const hasErrors = p.error_count > 0;
              const hasWarnings = p.warning_count > 0;

              return (
                <div
                  key={p.id}
                  onClick={() => setActivePageId(p.id)}
                  className={`group/pg w-full px-3 py-2 rounded-lg text-xs flex items-center justify-between border cursor-pointer transition-all ${
                    isPageActive
                      ? "bg-indigo-50 dark:bg-indigo-950/40 border-indigo-500/40 text-indigo-900 dark:text-indigo-200 font-semibold"
                      : "bg-transparent border-transparent text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800/60 hover:text-slate-900 dark:hover:text-slate-200"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    {isRefreshing ? (
                      <RefreshCw className="w-3.5 h-3.5 text-indigo-600 dark:text-indigo-400 animate-spin" />
                    ) : (
                      <span>Page {p.page_number}</span>
                    )}
                    <span className="text-[10px] text-slate-400">({p.record_count}r)</span>
                  </div>

                  <div className="flex items-center gap-1">
                    {/* Refresh Page Icon Button */}
                    <button
                      onClick={(e) => handleRefreshPageClick(e, p.id)}
                      disabled={isRefreshing}
                      className="p-1 rounded text-slate-400 opacity-0 group-hover/pg:opacity-100 hover:text-indigo-600 dark:hover:text-indigo-400 hover:bg-slate-200 dark:hover:bg-slate-700 transition-all"
                      title="Refresh Page (Re-run OCR for this page only)"
                    >
                      <RefreshCw className={`w-3 h-3 ${isRefreshing ? "animate-spin" : ""}`} />
                    </button>

                    {hasErrors && (
                      <span className="px-1.5 py-0.2 rounded-full bg-rose-500/10 text-rose-600 dark:text-rose-400 text-[10px] font-bold border border-rose-500/20">
                        {p.error_count}
                      </span>
                    )}
                    {hasWarnings && !hasErrors && (
                      <span className="px-1.5 py-0.2 rounded-full bg-amber-500/10 text-amber-600 dark:text-amber-400 text-[10px] font-bold border border-amber-500/20">
                        {p.warning_count}
                      </span>
                    )}
                    {!hasErrors && !hasWarnings && p.record_count > 0 && (
                      <CheckCircle className="w-3.5 h-3.5 text-emerald-500" />
                    )}
                  </div>
                </div>
              );
            })}

            {pagesIndex.length === 0 && !isLoadingPages && (
              <p className="text-center text-[11px] text-slate-400 py-4">
                No pages extracted yet. Click Run OCR to begin.
              </p>
            )}
          </div>
        </div>
      )}
    </aside>
  );
};

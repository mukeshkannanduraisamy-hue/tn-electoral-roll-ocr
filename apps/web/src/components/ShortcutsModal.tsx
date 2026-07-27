"use client";

import React from "react";
import { Keyboard, X } from "lucide-react";
import { useOcrStore } from "@/store/useOcrStore";

export const ShortcutsModal: React.FC = () => {
  const { isShortcutsOpen, setIsShortcutsOpen } = useOcrStore();

  if (!isShortcutsOpen) return null;

  const shortcuts = [
    { key: "R", description: "Re-run OCR on active page (Page-by-Page Refresh)" },
    { key: "J / K", description: "Navigate to next / previous record row" },
    { key: "Enter", description: "Edit focused field cell / Save edit" },
    { key: "Esc", description: "Cancel active edit / Close modal" },
    { key: "Space", description: "Toggle record reviewed / approved status" },
    { key: "/", description: "Focus text search filter" },
    { key: "1 / 2 / 3", description: "Switch view: Table / Page Image / Review Queue" },
    { key: "?", description: "Toggle keyboard shortcuts reference modal" },
  ];

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/80 dark:bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl w-full max-w-lg shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        {/* Modal Header */}
        <div className="px-5 py-4 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2 text-slate-900 dark:text-slate-100 font-bold text-base">
            <Keyboard className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
            <span>Keyboard Shortcuts</span>
          </div>
          <button
            onClick={() => setIsShortcutsOpen(false)}
            className="p-1 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Shortcuts List */}
        <div className="p-5 space-y-3">
          {shortcuts.map((s, idx) => (
            <div
              key={idx}
              className="flex items-center justify-between p-2.5 rounded-lg bg-slate-50 dark:bg-slate-950/60 border border-slate-200/80 dark:border-slate-800/80"
            >
              <span className="text-xs text-slate-600 dark:text-slate-300 font-medium">
                {s.description}
              </span>
              <kbd className="px-2.5 py-1 rounded bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 shadow-sm text-xs font-mono font-semibold text-indigo-600 dark:text-indigo-400">
                {s.key}
              </kbd>
            </div>
          ))}
        </div>

        {/* Modal Footer */}
        <div className="px-5 py-3 bg-slate-50 dark:bg-slate-950 border-t border-slate-200 dark:border-slate-800 text-center text-xs text-slate-500 dark:text-slate-400">
          Press <kbd className="px-1.5 py-0.5 rounded bg-slate-200 dark:bg-slate-800 font-mono text-[10px]">Esc</kbd> anytime to dismiss
        </div>
      </div>
    </div>
  );
};

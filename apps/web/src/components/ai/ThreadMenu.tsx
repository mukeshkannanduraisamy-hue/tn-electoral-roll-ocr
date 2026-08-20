"use client";

/** Past conversations. Opening one replays exactly what was shown at the time. */

import React, { useEffect, useState } from "react";
import { History, Plus, Trash2 } from "lucide-react";
import type { ChatThreadSummary } from "@ocr/shared-types";

interface Props {
  threads: ChatThreadSummary[];
  activeId: string | null;
  onNew: () => void;
  onOpen: (id: string) => void;
  onDelete: (id: string) => void;
  onRefresh: () => void;
}

export const ThreadMenu: React.FC<Props> = ({
  threads, activeId, onNew, onOpen, onDelete, onRefresh,
}) => {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (open) {
      onRefresh();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  return (
    <div className="relative">
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={onNew}
          aria-label="Start a new conversation"
          className="w-8 h-8 rounded-xl bg-slate-800/80 hover:bg-slate-700 text-slate-400 hover:text-white grid place-items-center transition-colors"
        >
          <Plus className="w-4 h-4" />
        </button>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-label="Past conversations"
          className="w-8 h-8 rounded-xl bg-slate-800/80 hover:bg-slate-700 text-slate-400 hover:text-white grid place-items-center transition-colors"
        >
          <History className="w-4 h-4" />
        </button>
      </div>

      {open && (
        <div className="absolute right-0 top-10 z-10 w-64 max-h-72 overflow-y-auto rounded-xl border border-slate-700 bg-slate-900 shadow-2xl p-1">
          {threads.length === 0 ? (
            <p className="p-3 text-[11px] text-slate-500">No past conversations.</p>
          ) : (
            threads.map((t) => (
              <div
                key={t.id}
                className={`flex items-center gap-1 rounded-lg px-2 py-1.5 text-[11px] ${
                  t.id === activeId ? "bg-indigo-500/20 text-indigo-200" : "text-slate-300 hover:bg-slate-800"
                }`}
              >
                <button
                  type="button"
                  onClick={() => { onOpen(t.id); setOpen(false); }}
                  className="flex-1 text-left truncate"
                  title={t.title}
                >
                  {t.title || "Untitled"}
                </button>
                <button
                  type="button"
                  onClick={() => onDelete(t.id)}
                  aria-label={`Delete ${t.title}`}
                  className="text-slate-500 hover:text-rose-400 transition-colors shrink-0"
                >
                  <Trash2 className="w-3 h-3" />
                </button>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
};

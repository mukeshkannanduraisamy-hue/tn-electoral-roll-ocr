"use client";

/**
 * What the assistant actually did.
 *
 * Collapsed by default — most of the time the answer is the point. Expanded, it
 * shows every step, because an answer whose workings cannot be inspected is an
 * answer that has to be taken on trust.
 */

import React, { useState } from "react";
import { CheckCircle2, ChevronRight, XCircle } from "lucide-react";
import type { ChatToolStep } from "@ocr/shared-types";

export const ToolTrace: React.FC<{ steps: ChatToolStep[] }> = ({ steps }) => {
  const [open, setOpen] = useState(false);
  if (!steps.length) return null;

  return (
    <div className="mt-2 text-[10px]">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1 text-slate-400 hover:text-slate-200 font-bold uppercase tracking-wide transition-colors"
      >
        <ChevronRight className={`w-3 h-3 transition-transform ${open ? "rotate-90" : ""}`} />
        Ran {steps.length} step{steps.length === 1 ? "" : "s"}
      </button>

      {open && (
        <ul className="mt-1.5 space-y-1 border-l border-slate-700 pl-2.5">
          {steps.map((step, i) => (
            <li key={`${step.tool}-${i}`} className="flex items-start gap-1.5 font-mono text-slate-400">
              {step.ok ? (
                <CheckCircle2 className="w-3 h-3 text-emerald-400 shrink-0 mt-0.5" />
              ) : (
                <XCircle className="w-3 h-3 text-rose-400 shrink-0 mt-0.5" />
              )}
              <span className="break-all">
                <span className="text-slate-300">{step.tool}</span>
                {step.args && Object.keys(step.args).length > 0 && (
                  <span>
                    (
                    {Object.entries(step.args)
                      .map(([k, v]) => `${k}=${String(v)}`)
                      .join(", ")}
                    )
                  </span>
                )}
                {step.ok
                  ? step.returned != null && <span className="text-slate-500"> → {step.returned} rows</span>
                  : <span className="text-rose-400"> → {step.error}</span>}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

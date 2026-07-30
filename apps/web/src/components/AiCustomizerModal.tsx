"use client";

import React, { useState, useEffect } from "react";
import {
  Sparkles,
  Palette,
  Filter,
  Columns,
  Download,
  RotateCcw,
  Save,
  CheckCircle2,
  X,
  Zap,
  ArrowRight,
} from "lucide-react";
import { toast } from "sonner";
import { queryAiCopilot } from "@/lib/voterApi";
import type { Infographic } from "@ocr/shared-types";
import { InfographicCard } from "./InfographicCard";

/**
 * One line in the transcript. A statistical question also carries a chart of
 * real figures, so the assistant answers in prose or in a chart depending on
 * what was asked.
 */
interface LogEntry {
  text: string;
  isAi?: boolean;
  infographic?: Infographic | null;
}

export interface AiCustomizerProps {
  isOpen: boolean;
  onClose: () => void;
  onApplyTheme: (theme: string) => void;
  onApplyFilter: (filters: {
    gender?: string;
    minAge?: string;
    maxAge?: string;
    verified?: string;
    houseNumber?: string;
    relationType?: string;
  }) => void;
  onApplyColumns: (preset: "all" | "basic" | "identity") => void;
  onTriggerExport: (format: "excel" | "csv" | "json") => void;
  onResetAll: () => void;
}

export const AiCustomizerModal: React.FC<AiCustomizerProps> = ({
  isOpen,
  onClose,
  onApplyTheme,
  onApplyFilter,
  onApplyColumns,
  onTriggerExport,
  onResetAll,
}) => {
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [savedPresetName, setSavedPresetName] = useState<string | null>(null);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const saved = localStorage.getItem("ai_custom_workspace_preset");
      if (saved) {
        try {
          const parsed = JSON.parse(saved);
          setSavedPresetName(parsed.name || "Custom AI Workspace");
        } catch {}
      }
    }
  }, []);

  if (!isOpen) return null;

  const processAiPrompt = async (userPrompt: string) => {
    if (!userPrompt.trim()) return;

    const inputMsg = userPrompt.trim();
    setPrompt("");
    setLoading(true);

    const actions: string[] = [];

    try {
      // 1. Call Backend NVIDIA AI Copilot API (z-ai/glm-5.2)
      const res = await queryAiCopilot(inputMsg);

      if (res.reply || res.infographic) {
        setLogs((prev) => [
          {
            text: res.reply || res.infographic?.title || "",
            isAi: true,
            infographic: res.infographic ?? null,
          },
          ...prev,
        ]);
      }

      const ui = res.ui_changes || {};

      if (ui.theme) {
        onApplyTheme(String(ui.theme));
        actions.push(`Theme: Switched to ${ui.theme}`);
      }
      if (ui.filters && typeof ui.filters === "object") {
        onApplyFilter(ui.filters as any);
        actions.push("Filters: Applied custom criteria");
      }
      if (ui.columns) {
        onApplyColumns(ui.columns as any);
        actions.push(`Columns: Switched to ${ui.columns}`);
      }
      if (ui.export) {
        onTriggerExport(ui.export as any);
        actions.push(`Export: Triggered ${ui.export}`);
      }
      if (ui.reset) {
        onResetAll();
        actions.push("Reset: Restored default settings");
      }
    } catch {
      // Local Client-side Rule Engine Fallback
      const p = inputMsg.toLowerCase();
      if (p.includes("emerald") || p.includes("green")) {
        onApplyTheme("emerald");
        actions.push("Theme set to Emerald Green");
      } else if (p.includes("purple") || p.includes("cyber")) {
        onApplyTheme("purple");
        actions.push("Theme set to Cyberpunk Purple");
      } else if (p.includes("amber") || p.includes("sunset")) {
        onApplyTheme("amber");
        actions.push("Theme set to Sunset Amber");
      } else if (p.includes("dark")) {
        onApplyTheme("dark");
        actions.push("Theme set to Dark Mode");
      } else if (p.includes("light")) {
        onApplyTheme("light");
        actions.push("Theme set to Light Mode");
      }

      if (p.includes("excel") || p.includes("xlsx")) {
        onTriggerExport("excel");
        actions.push("Action: Triggered Excel export download");
      } else if (p.includes("csv")) {
        onTriggerExport("csv");
        actions.push("Action: Triggered CSV export download");
      }

      if (p.includes("reset") || p.includes("default")) {
        onResetAll();
        actions.push("Reset: Reverted all UI settings to default");
      }

      setLogs((prev) => [{ text: `AI Assistant: Processed "${inputMsg}"`, isAi: true }, ...prev]);
    } finally {
      setLoading(false);
    }

    if (actions.length > 0) {
      toast.success(`AI applied ${actions.length} UI customization(s)`);
      setLogs((prev) => [...actions.map((a) => ({ text: a, isAi: false })), ...prev]);
    }
  };

  const handleSavePreset = () => {
    if (typeof window !== "undefined") {
      const presetData = {
        name: "Custom AI Workspace",
        timestamp: new Date().toISOString(),
      };
      localStorage.setItem("ai_custom_workspace_preset", JSON.stringify(presetData));
      setSavedPresetName("Custom AI Workspace");
      toast.success("Saved AI Workspace Preset successfully!");
    }
  };

  const handleReset = () => {
    onResetAll();
    if (typeof window !== "undefined") {
      localStorage.removeItem("ai_custom_workspace_preset");
    }
    setSavedPresetName(null);
    setLogs([{ text: "UI and filters reset to system defaults." }]);
    toast.info("Reset UI layout and filters to default");
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="card-vimc w-full max-w-2xl p-6 bg-slate-900 text-slate-100 border-indigo-500/40 shadow-2xl space-y-6 animate-in fade-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800 pb-4">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-2xl bg-gradient-to-tr from-indigo-500 via-purple-500 to-rose-500 flex items-center justify-center text-white font-black shadow-lg shadow-indigo-500/30">
              <Sparkles className="w-5 h-5 animate-pulse" />
            </div>
            <div>
              <h3 className="text-base font-extrabold text-white flex items-center space-x-2">
                <span>AI Workspace Customizer & Copilot</span>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-black uppercase bg-indigo-500/20 text-indigo-400 border border-indigo-500/40">
                  Live Copilot
                </span>
              </h3>
              <p className="text-xs text-slate-400">
                Type natural language instructions to customize UI themes, filters, columns, and export data.
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="w-8 h-8 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white flex items-center justify-center transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* AI Prompt Input Bar */}
        <div className="space-y-2">
          <label className="text-xs font-bold text-slate-300 flex items-center space-x-1.5">
            <Zap className="w-3.5 h-3.5 text-amber-400" />
            <span>Ask AI to Customize UI & Filters</span>
          </label>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              processAiPrompt(prompt);
            }}
            className="flex gap-2"
          >
            <input
              type="text"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="e.g. Switch to Emerald theme, show female voters 18-25, and export to Excel..."
              className="flex-1 bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
            />
            <button
              type="submit"
              className="px-4 py-2.5 bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white text-xs font-extrabold rounded-xl shadow-md flex items-center space-x-1.5 shrink-0"
            >
              <span>Apply AI</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </form>
        </div>

        {/* Quick Command Chips */}
        <div className="space-y-2">
          <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">
            Quick AI Customization Presets
          </span>

          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => processAiPrompt("Switch to Emerald theme")}
              className="px-2.5 py-1.5 rounded-lg bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 text-xs font-bold flex items-center space-x-1.5 transition-colors"
            >
              <Palette className="w-3 h-3" />
              <span>Emerald Theme</span>
            </button>

            <button
              onClick={() => processAiPrompt("Switch to Cyberpunk Purple theme")}
              className="px-2.5 py-1.5 rounded-lg bg-purple-500/10 hover:bg-purple-500/20 text-purple-400 border border-purple-500/30 text-xs font-bold flex items-center space-x-1.5 transition-colors"
            >
              <Palette className="w-3 h-3" />
              <span>Purple Theme</span>
            </button>

            <button
              onClick={() => processAiPrompt("Switch to Sunset Amber theme")}
              className="px-2.5 py-1.5 rounded-lg bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 border border-amber-500/30 text-xs font-bold flex items-center space-x-1.5 transition-colors"
            >
              <Palette className="w-3 h-3" />
              <span>Sunset Amber</span>
            </button>

            <button
              onClick={() => processAiPrompt("Filter female voters 18-25")}
              className="px-2.5 py-1.5 rounded-lg bg-indigo-500/10 hover:bg-indigo-500/20 text-indigo-400 border border-indigo-500/30 text-xs font-bold flex items-center space-x-1.5 transition-colors"
            >
              <Filter className="w-3 h-3" />
              <span>Young Female Voters (18-25)</span>
            </button>

            <button
              onClick={() => processAiPrompt("Filter unverified voters")}
              className="px-2.5 py-1.5 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/30 text-xs font-bold flex items-center space-x-1.5 transition-colors"
            >
              <Filter className="w-3 h-3" />
              <span>Unverified Voters</span>
            </button>

            <button
              onClick={() => processAiPrompt("Show all 23 columns")}
              className="px-2.5 py-1.5 rounded-lg bg-blue-500/10 hover:bg-blue-500/20 text-blue-400 border border-blue-500/30 text-xs font-bold flex items-center space-x-1.5 transition-colors"
            >
              <Columns className="w-3 h-3" />
              <span>All 23 Columns</span>
            </button>

            <button
              onClick={() => processAiPrompt("Export to Excel")}
              className="px-2.5 py-1.5 rounded-lg bg-teal-500/10 hover:bg-teal-500/20 text-teal-400 border border-teal-500/30 text-xs font-bold flex items-center space-x-1.5 transition-colors"
            >
              <Download className="w-3 h-3" />
              <span>Export Excel</span>
            </button>
          </div>
        </div>

        {/* AI Action Execution Log */}
        {logs.length > 0 && (
          <div className="space-y-1.5">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
              AI Conversation & Action Log
            </span>
            {/* Taller than a pure text log needs: a chart card has to be
                readable without scrolling it line by line. */}
            <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 text-slate-300 text-xs space-y-2 max-h-[26rem] overflow-y-auto">
              {logs.map((log, i) => (
                <div key={i} className="space-y-1">
                  <div className={`flex items-start space-x-2 ${log.isAi ? "text-indigo-300" : "text-emerald-400 font-mono text-[11px]"}`}>
                    {log.isAi ? (
                      <Sparkles className="w-3.5 h-3.5 text-indigo-400 shrink-0 mt-0.5" />
                    ) : (
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-0.5" />
                    )}
                    <span className="whitespace-pre-wrap leading-relaxed">{log.text}</span>
                  </div>
                  {log.infographic && <InfographicCard data={log.infographic} />}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Footer Actions: Save Preset & Reset */}
        <div className="flex items-center justify-between pt-4 border-t border-slate-800">
          <button
            onClick={handleReset}
            className="px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white text-xs font-bold flex items-center space-x-1.5 transition-colors"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>Reset UI to Default</span>
          </button>

          <div className="flex items-center space-x-3">
            {savedPresetName && (
              <span className="text-[11px] font-bold text-emerald-400 flex items-center space-x-1">
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>Saved Workspace</span>
              </span>
            )}

            <button
              onClick={handleSavePreset}
              className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-black rounded-xl shadow-md flex items-center space-x-1.5 transition-colors"
            >
              <Save className="w-3.5 h-3.5" />
              <span>Save AI Workspace</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

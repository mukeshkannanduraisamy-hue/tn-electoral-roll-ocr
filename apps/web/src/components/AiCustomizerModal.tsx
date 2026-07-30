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
  const [logs, setLogs] = useState<string[]>([]);
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

  const processAiPrompt = (userPrompt: string) => {
    if (!userPrompt.trim()) return;

    const p = userPrompt.toLowerCase().trim();
    const actions: string[] = [];

    // 1. Theme Customization
    if (p.includes("emerald") || p.includes("green")) {
      onApplyTheme("emerald");
      actions.push("Theme set to Emerald Green");
    } else if (p.includes("purple") || p.includes("cyber")) {
      onApplyTheme("purple");
      actions.push("Theme set to Cyberpunk Purple");
    } else if (p.includes("amber") || p.includes("sunset") || p.includes("gold")) {
      onApplyTheme("amber");
      actions.push("Theme set to Sunset Amber");
    } else if (p.includes("ocean") || p.includes("blue")) {
      onApplyTheme("ocean");
      actions.push("Theme set to Ocean Blue");
    } else if (p.includes("dark") || p.includes("night")) {
      onApplyTheme("dark");
      actions.push("Theme set to Dark Mode");
    } else if (p.includes("light") || p.includes("day")) {
      onApplyTheme("light");
      actions.push("Theme set to Light Mode");
    }

    // 2. Filter Rules
    const filters: any = {};
    if (p.includes("female") || p.includes("women")) {
      filters.gender = "Female";
      actions.push("Filter set: Gender = Female");
    } else if (p.includes("male") || p.includes("men")) {
      filters.gender = "Male";
      actions.push("Filter set: Gender = Male");
    }

    if (p.includes("18-25") || p.includes("young")) {
      filters.minAge = "18";
      filters.maxAge = "25";
      actions.push("Filter set: Age 18–25");
    } else if (p.includes("26-40") || p.includes("adult")) {
      filters.minAge = "26";
      filters.maxAge = "40";
      actions.push("Filter set: Age 26–40");
    } else if (p.includes("senior") || p.includes("60+")) {
      filters.minAge = "60";
      filters.maxAge = "120";
      actions.push("Filter set: Senior Voters (60+)");
    }

    if (p.includes("unverified") || p.includes("pending")) {
      filters.verified = "false";
      actions.push("Filter set: Unverified Voters Only");
    } else if (p.includes("verified")) {
      filters.verified = "true";
      actions.push("Filter set: Verified Voters Only");
    }

    if (Object.keys(filters).length > 0) {
      onApplyFilter(filters);
    }

    // 3. Column Layouts
    if (p.includes("all columns") || p.includes("23 columns") || p.includes("full columns")) {
      onApplyColumns("all");
      actions.push("Columns: Enabled all 23 database columns");
    } else if (p.includes("basic columns") || p.includes("minimal")) {
      onApplyColumns("basic");
      actions.push("Columns: Enabled basic columns");
    } else if (p.includes("identity") || p.includes("voter identity")) {
      onApplyColumns("identity");
      actions.push("Columns: Enabled identity columns");
    }

    // 4. Export Actions
    if (p.includes("excel") || p.includes("xlsx")) {
      onTriggerExport("excel");
      actions.push("Action: Triggered Excel export download");
    } else if (p.includes("csv")) {
      onTriggerExport("csv");
      actions.push("Action: Triggered CSV export download");
    }

    // 5. Reset Command
    if (p.includes("reset") || p.includes("default") || p.includes("clear")) {
      onResetAll();
      actions.push("Reset: Reverted all UI themes, filters, and columns to default");
    }

    if (actions.length === 0) {
      actions.push(`Interpreted query: "${userPrompt}" -> Customizing UI view.`);
      toast.info(`AI processed: "${userPrompt}"`);
    } else {
      toast.success(`AI applied ${actions.length} UI customization(s)`);
    }

    setLogs((prev) => [...actions, ...prev]);
    setPrompt("");
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
    setLogs(["UI and filters reset to system defaults."]);
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
              AI Action History
            </span>
            <div className="p-3 rounded-xl bg-slate-950 border border-slate-800 text-slate-300 font-mono text-[11px] space-y-1 max-h-32 overflow-y-auto">
              {logs.map((log, i) => (
                <div key={i} className="flex items-center space-x-2 text-emerald-400">
                  <CheckCircle2 className="w-3 h-3 shrink-0" />
                  <span className="truncate">{log}</span>
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

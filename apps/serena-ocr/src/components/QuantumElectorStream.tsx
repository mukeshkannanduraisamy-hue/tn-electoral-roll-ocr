"use client";

import React, { useState, useMemo } from "react";
import {
  Users,
  Search,
  Download,
  Copy,
  Check,
  ExternalLink,
  ShieldCheck,
  Sparkles,
  Database,
  ArrowUpRight,
  Filter,
  Loader2,
  FileSpreadsheet,
} from "lucide-react";
import { useSerenaStore } from "@/store/useSerenaStore";
import { toast } from "sonner";

export const QuantumElectorStream: React.FC = () => {
  const {
    selectedItem,
    liveExtractedElectors,
    isLoadingElectors,
    setActiveTab,
  } = useSerenaStore();

  const [electorSearch, setElectorSearch] = useState("");
  const [copiedEpic, setCopiedEpic] = useState<string | null>(null);

  const filteredElectors = useMemo(() => {
    if (!liveExtractedElectors || liveExtractedElectors.length === 0) return [];
    if (!electorSearch.trim()) return liveExtractedElectors;
    const q = electorSearch.toLowerCase();
    return liveExtractedElectors.filter((r) => {
      const epic = (r.epic_number || r.voter_id || "").toLowerCase();
      const name = (r.name_ta || r.name || "").toLowerCase();
      const relName = (r.relative_name_ta || r.relation_name || "").toLowerCase();
      const house = (r.house_number || "").toLowerCase();
      return epic.includes(q) || name.includes(q) || relName.includes(q) || house.includes(q);
    });
  }, [liveExtractedElectors, electorSearch]);

  const handleCopyEpic = (epic: string) => {
    navigator.clipboard.writeText(epic);
    setCopiedEpic(epic);
    toast.success(`Copied EPIC: ${epic}`);
    setTimeout(() => setCopiedEpic(null), 2000);
  };

  const handleExportCsv = () => {
    if (filteredElectors.length === 0) {
      toast.error("No electors available to export");
      return;
    }
    const headers = ["Serial_No", "EPIC_Number", "Name_Tamil", "Relation_Type", "Relation_Name", "House_No", "Age", "Gender", "Deleted"];
    const rows = filteredElectors.map((e, idx) => [
      e.serial_number || idx + 1,
      `"${e.epic_number || e.voter_id || ""}"`,
      `"${e.name_ta || e.name || ""}"`,
      `"${e.relation_type_ta || e.relation_type || ""}"`,
      `"${e.relative_name_ta || e.relation_name || ""}"`,
      `"${e.house_number || ""}"`,
      e.age || "",
      `"${e.gender_ta || e.gender || ""}"`,
      e.is_deleted ? "YES" : "NO",
    ]);

    const csvContent = "data:text/csv;charset=utf-8,\uFEFF" + [headers.join(","), ...rows.map((r) => r.join(","))].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `${selectedItem?.name || "elector_records"}_curated.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    toast.success("Exported curated CSV file successfully");
  };

  return (
    <aside className="w-80 lg:w-96 serena-glass rounded-3xl border border-slate-200 dark:border-white/5 flex flex-col min-h-0 overflow-hidden shrink-0 shadow-xs">
      {/* Top Header & Search */}
      <div className="p-4 border-b border-slate-200 dark:border-white/5 space-y-3 bg-slate-50/50 dark:bg-obsidian-950/40 shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center">
              <Users className="w-4 h-4 text-emerald-500" />
            </div>
            <div>
              <h3 className="text-xs font-black uppercase tracking-wider text-slate-800 dark:text-slate-200">
                Elector Vault
              </h3>
              <p className="text-[10px] text-slate-400 font-mono">
                {filteredElectors.length} Curated Voters
              </p>
            </div>
          </div>

          <div className="flex items-center gap-1.5">
            <button
              onClick={handleExportCsv}
              className="p-1.5 rounded-xl bg-slate-100 dark:bg-obsidian-950 hover:bg-slate-200 dark:hover:bg-obsidian-850 border border-slate-200 dark:border-white/10 text-slate-700 dark:text-slate-300 transition-colors shadow-xs"
              title="Export Curated CSV"
            >
              <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-500" />
            </button>

            <button
              onClick={() => setActiveTab("database")}
              className="flex items-center gap-1 px-2 py-1 rounded-xl bg-serena-indigo/10 hover:bg-serena-indigo/20 border border-serena-indigo/30 text-serena-indigo text-[11px] font-bold transition-colors"
              title="Open in Database Explorer"
            >
              <span>DB</span>
              <ArrowUpRight className="w-3 h-3" />
            </button>
          </div>
        </div>

        {/* Elector Search */}
        <div className="relative">
          <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="Search EPIC, Name, House #…"
            value={electorSearch}
            onChange={(e) => setElectorSearch(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 bg-white dark:bg-obsidian-950 border border-slate-200 dark:border-white/10 rounded-xl text-xs text-slate-900 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 focus:outline-none focus:ring-1 focus:ring-emerald-500 shadow-inner font-mono"
          />
        </div>
      </div>

      {/* Elector Stream Cards */}
      <div className="flex-1 overflow-y-auto p-2.5 space-y-2">
        {isLoadingElectors ? (
          <div className="flex flex-col items-center justify-center h-48 text-center p-4 text-slate-400">
            <Loader2 className="w-7 h-7 animate-spin text-emerald-500 mb-2" />
            <span className="text-xs font-semibold">Streaming curated electors…</span>
          </div>
        ) : filteredElectors.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-48 text-center p-4 text-slate-400">
            <Users className="w-8 h-8 opacity-40 mb-2" />
            <span className="text-xs font-semibold">No Electors in Buffer</span>
            <p className="text-[11px] text-slate-500 mt-1">
              Process this Part to decode and stream voter records live
            </p>
          </div>
        ) : (
          filteredElectors.map((elector, idx) => {
            const epic = elector.epic_number || elector.voter_id || `TN-${1000 + idx}`;
            const name = elector.name_ta || elector.name || "—";
            const relType = elector.relation_type_ta || elector.relation_type || "தந்தை";
            const relName = elector.relative_name_ta || elector.relation_name || "—";
            const house = elector.house_number || "—";
            const age = elector.age || "—";
            const gender = elector.gender_ta || elector.gender || "—";
            const isDeleted = Boolean(elector.is_deleted);

            return (
              <div
                key={idx}
                className={`p-3 rounded-2xl border transition-all ${
                  isDeleted
                    ? "bg-rose-500/5 border-rose-500/30 opacity-75"
                    : "bg-white/60 dark:bg-obsidian-950/60 border-slate-200 dark:border-white/5 hover:border-emerald-500/40"
                }`}
              >
                {/* Top Row: Serial # & EPIC */}
                <div className="flex items-center justify-between gap-2">
                  <span className="px-2 py-0.5 rounded-md font-mono font-bold text-[10px] bg-slate-100 dark:bg-obsidian-900 text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-white/10">
                    #{elector.serial_number || idx + 1}
                  </span>

                  <button
                    onClick={() => handleCopyEpic(epic)}
                    className="flex items-center gap-1 font-mono text-[11px] font-bold text-serena-indigo hover:text-indigo-400 transition-colors"
                  >
                    <span>{epic}</span>
                    {copiedEpic === epic ? (
                      <Check className="w-3 h-3 text-emerald-500" />
                    ) : (
                      <Copy className="w-3 h-3 opacity-60" />
                    )}
                  </button>
                </div>

                {/* Name in Tamil */}
                <div className="mt-2">
                  <div className="text-xs font-bold text-slate-900 dark:text-white">
                    {name}
                  </div>
                  <div className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">
                    {relType}: <span className="text-slate-700 dark:text-slate-300">{relName}</span>
                  </div>
                </div>

                {/* Badges: House, Age, Gender */}
                <div className="flex items-center gap-1.5 mt-2 flex-wrap font-mono text-[10px]">
                  <span className="px-2 py-0.5 rounded-md bg-slate-100 dark:bg-obsidian-900 text-slate-600 dark:text-slate-300">
                    H: {house}
                  </span>
                  <span className="px-2 py-0.5 rounded-md bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20">
                    Age: {age}
                  </span>
                  <span
                    className={`px-2 py-0.5 rounded-md border ${
                      gender.includes("பெண்") || gender.toLowerCase().includes("female")
                        ? "bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20"
                        : "bg-cyan-500/10 text-cyan-600 dark:text-cyan-400 border-cyan-500/20"
                    }`}
                  >
                    {gender}
                  </span>
                  {isDeleted && (
                    <span className="px-2 py-0.5 rounded-md bg-rose-500/20 text-rose-500 font-bold border border-rose-500/40">
                      DELETED
                    </span>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
};

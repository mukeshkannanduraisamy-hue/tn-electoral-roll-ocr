import React, { useEffect, useState } from "react";
import { useOcrStore } from "@/store/useOcrStore";
import { useTheme } from "next-themes";
import {
  Search,
  LayoutDashboard,
  Users,
  FileText,
  PieChart,
  Settings,
  Upload,
  Download,
  Moon,
  Sun,
  X,
  FileSpreadsheet,
  CheckCircle2,
  HelpCircle,
  Building2,
  CheckSquare,
  Sparkles,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface CommandPaletteProps {
  isOpen: boolean;
  onClose: () => void;
  onOpenUpload: () => void;
  onOpenExport: () => void;
  onOpenBulkExtract: () => void;
}

export function CommandPalette({
  isOpen,
  onClose,
  onOpenUpload,
  onOpenExport,
  onOpenBulkExtract,
}: CommandPaletteProps) {
  const { setActiveTab, files, voters } = useOcrStore();
  const { theme, setTheme } = useTheme();
  const [query, setQuery] = useState("");

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        if (isOpen) onClose();
        else {
          setQuery("");
          // Open handled by parent
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const navigateTo = (tab: any) => {
    setActiveTab(tab);
    onClose();
  };

  const filteredFiles = files.filter(f => f.name.toLowerCase().includes(query.toLowerCase())).slice(0, 4);
  const filteredVoters = voters.filter(v => 
    v.name.toLowerCase().includes(query.toLowerCase()) || 
    (v.epic || (v as any).epic_id || "").toLowerCase().includes(query.toLowerCase())
  ).slice(0, 5);

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-20 px-4 bg-slate-950/60 backdrop-blur-sm animate-fade-slide">
      <div
        className="fixed inset-0"
        onClick={onClose}
        aria-hidden="true"
      />
      <div className="relative w-full max-w-2xl rounded-xl glass shadow-2xl border border-border overflow-hidden z-10 animate-scale-in">
        {/* Search Header */}
        <div className="flex items-center px-4 border-b border-border/60 bg-muted/30">
          <Search className="w-5 h-5 text-muted-foreground mr-3 shrink-0" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Type a command or search voters, EPIC IDs, files... (Try 'male above 60')"
            className="w-full h-12 bg-transparent text-foreground placeholder:text-muted-foreground text-sm focus:outline-none"
            autoFocus
          />
          {query && (
            <button
              onClick={() => setQuery("")}
              className="p-1 rounded-md text-muted-foreground hover:text-foreground mr-2"
            >
              <X className="w-4 h-4" />
            </button>
          )}
          <span className="text-[11px] font-mono-code px-1.5 py-0.5 rounded bg-muted border border-border text-muted-foreground select-none">
            ESC
          </span>
        </div>

        {/* Results Container */}
        <div className="max-h-96 overflow-y-auto p-2 space-y-3">
          {/* Quick AI Search Hints */}
          {query && (
            <div className="px-2 py-1.5 text-xs text-indigo-500 font-medium flex items-center gap-1.5 border-b border-border/40 pb-2">
              <Sparkles className="w-3.5 h-3.5" />
              <span>Smart Query Filter: &ldquo;{query}&rdquo; — Press Enter to filter Voter Directory</span>
            </div>
          )}

          {/* Navigation Items */}
          <div>
            <div className="px-2 py-1 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
              Navigation
            </div>
            <div className="space-y-0.5">
              <button
                onClick={() => navigateTo("dashboard")}
                className="w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm hover:bg-primary/10 hover:text-primary transition-colors text-left"
              >
                <div className="flex items-center gap-2.5">
                  <LayoutDashboard className="w-4 h-4 text-indigo-500" />
                  <span>Dashboard</span>
                </div>
                <span className="text-[11px] text-muted-foreground font-mono-code">Key 1</span>
              </button>
              <button
                onClick={() => navigateTo("voters")}
                className="w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm hover:bg-primary/10 hover:text-primary transition-colors text-left"
              >
                <div className="flex items-center gap-2.5">
                  <Users className="w-4 h-4 text-blue-500" />
                  <span>Voter Directory</span>
                </div>
                <span className="text-[11px] text-muted-foreground font-mono-code">Key 2</span>
              </button>
              <button
                onClick={() => navigateTo("polling_stations")}
                className="w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm hover:bg-primary/10 hover:text-primary transition-colors text-left"
              >
                <div className="flex items-center gap-2.5">
                  <Building2 className="w-4 h-4 text-teal-500" />
                  <span>Polling Stations</span>
                </div>
                <span className="text-[11px] text-muted-foreground font-mono-code">Key 3</span>
              </button>
              <button
                onClick={() => navigateTo("table")}
                className="w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm hover:bg-primary/10 hover:text-primary transition-colors text-left"
              >
                <div className="flex items-center gap-2.5">
                  <FileText className="w-4 h-4 text-violet-500" />
                  <span>Document Manager</span>
                </div>
                <span className="text-[11px] text-muted-foreground font-mono-code">Key 4</span>
              </button>
              <button
                onClick={() => navigateTo("analytics")}
                className="w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm hover:bg-primary/10 hover:text-primary transition-colors text-left"
              >
                <div className="flex items-center gap-2.5">
                  <PieChart className="w-4 h-4 text-emerald-500" />
                  <span>Analytics & Intelligence</span>
                </div>
                <span className="text-[11px] text-muted-foreground font-mono-code">Key 5</span>
              </button>
              <button
                onClick={() => navigateTo("review")}
                className="w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm hover:bg-primary/10 hover:text-primary transition-colors text-left"
              >
                <div className="flex items-center gap-2.5">
                  <CheckSquare className="w-4 h-4 text-amber-500" />
                  <span>Review Queue</span>
                </div>
                <span className="text-[11px] text-muted-foreground font-mono-code">Key 6</span>
              </button>
            </div>
          </div>

          {/* Quick Actions */}
          <div>
            <div className="px-2 py-1 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
              Quick Actions
            </div>
            <div className="space-y-0.5">
              <button
                onClick={() => {
                  onClose();
                  onOpenUpload();
                }}
                className="w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm hover:bg-primary/10 hover:text-primary transition-colors text-left"
              >
                <div className="flex items-center gap-2.5">
                  <Upload className="w-4 h-4 text-indigo-500" />
                  <span>Upload Electoral Roll PDF</span>
                </div>
              </button>
              <button
                onClick={() => {
                  onClose();
                  onOpenBulkExtract();
                }}
                className="w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm hover:bg-primary/10 hover:text-primary transition-colors text-left"
              >
                <div className="flex items-center gap-2.5">
                  <FileSpreadsheet className="w-4 h-4 text-violet-500" />
                  <span>Run Batch OCR Extraction</span>
                </div>
              </button>
              <button
                onClick={() => {
                  onClose();
                  onOpenExport();
                }}
                className="w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm hover:bg-primary/10 hover:text-primary transition-colors text-left"
              >
                <div className="flex items-center gap-2.5">
                  <Download className="w-4 h-4 text-emerald-500" />
                  <span>Export Data (Excel, CSV, PDF)</span>
                </div>
              </button>
              <button
                onClick={() => {
                  setTheme(theme === "dark" ? "light" : "dark");
                  onClose();
                }}
                className="w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm hover:bg-primary/10 hover:text-primary transition-colors text-left"
              >
                <div className="flex items-center gap-2.5">
                  {theme === "dark" ? <Sun className="w-4 h-4 text-amber-500" /> : <Moon className="w-4 h-4 text-slate-500" />}
                  <span>Toggle {theme === "dark" ? "Light" : "Dark"} Mode</span>
                </div>
              </button>
            </div>
          </div>

          {/* Voter Results */}
          {filteredVoters.length > 0 && (
            <div>
              <div className="px-2 py-1 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                Voters ({filteredVoters.length})
              </div>
              <div className="space-y-0.5">
                {filteredVoters.map((v) => (
                  <button
                    key={v.id}
                    onClick={() => navigateTo("voters")}
                    className="w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm hover:bg-primary/10 hover:text-primary transition-colors text-left"
                  >
                    <div className="flex items-center gap-2.5">
                      <span className="epic-chip text-[11px]">{v.epic || (v as any).epic_id || ""}</span>
                      <span className="font-medium text-foreground">{v.name}</span>
                    </div>
                    <span className="text-xs text-muted-foreground">{v.gender} • {v.age} yrs</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* File Results */}
          {filteredFiles.length > 0 && (
            <div>
              <div className="px-2 py-1 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                Documents ({filteredFiles.length})
              </div>
              <div className="space-y-0.5">
                {filteredFiles.map((f) => (
                  <button
                    key={f.id}
                    onClick={() => navigateTo("table")}
                    className="w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm hover:bg-primary/10 hover:text-primary transition-colors text-left"
                  >
                    <div className="flex items-center gap-2.5">
                      <FileText className="w-4 h-4 text-muted-foreground" />
                      <span className="font-medium text-foreground truncate max-w-xs">{f.name}</span>
                    </div>
                    <span className="text-xs text-muted-foreground">{f.page_count} pages</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-4 py-2 bg-muted/40 border-t border-border/50 text-[11px] text-muted-foreground flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span>Navigation: <kbd className="font-mono-code bg-muted px-1 rounded">↑</kbd> <kbd className="font-mono-code bg-muted px-1 rounded">↓</kbd></span>
            <span>Select: <kbd className="font-mono-code bg-muted px-1 rounded">↵</kbd></span>
          </div>
          <span className="flex items-center gap-1"><HelpCircle className="w-3 h-3" /> Press ? for shortcuts</span>
        </div>
      </div>
    </div>
  );
}

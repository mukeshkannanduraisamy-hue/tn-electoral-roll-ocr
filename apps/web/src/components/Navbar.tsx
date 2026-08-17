"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  Upload,
  Play,
  Pause,
  XSquare,
  Sun,
  Moon,
  Keyboard,
  LogOut,
  Search,
  Bell,
  Zap,
  User,
  ChevronDown,
  X,
  Loader2,
  Sparkles,
  Trash2,
} from "lucide-react";
import { useAuthStore } from "@/store/useAuthStore";
import { useOcrStore } from "@/store/useOcrStore";
import { listVoters } from "@/lib/voterApi";

interface NavbarProps {
  onOpenUpload: () => void;
  onOpenExport: () => void;
  onOpenBulkExtract: () => void;
}

interface SearchResult {
  id: string;
  epic: string;
  name: string;
  gender: string;
  age: number | null;
  house_number: string;
  part_number: string;
}

export const Navbar: React.FC<NavbarProps> = ({
  onOpenUpload,
  onOpenExport,
  onOpenBulkExtract,
}) => {
  const authUser = useAuthStore((s) => s.user);
  const signOut = useAuthStore((s) => s.signOut);

  const {
    theme,
    toggleTheme,
    activeJobStatus,
    activeJobProgress,
    pagesPerSec,
    etaSeconds,
    pauseJob,
    resumeJob,
    cancelJob,
    setIsShortcutsOpen,
    setActiveTab,
    setConfirmModal,
    resetAllData,
  } = useOcrStore();

  const handleClearDatabase = () => {
    setUserMenuOpen(false);
    setConfirmModal({
      isOpen: true,
      title: "Delete All Data in Database?",
      message:
        "This will permanently delete all voter records, polling stations, summary counts, and uploaded PDF documents from PostgreSQL and clear local storage caches. This action cannot be undone.",
      confirmText: "Delete All Data",
      danger: true,
      onConfirm: async () => {
        await resetAllData();
      },
    });
  };

  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const searchRef = useRef<HTMLDivElement>(null);
  const searchTimerRef = useRef<NodeJS.Timeout | null>(null);
  const userMenuRef = useRef<HTMLDivElement>(null);

  // Debounced search
  useEffect(() => {
    if (!searchQuery.trim() || searchQuery.length < 2) {
      setSearchResults([]);
      setSearchOpen(false);
      return;
    }
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    searchTimerRef.current = setTimeout(async () => {
      setSearchLoading(true);
      try {
        const data = await listVoters({ search: searchQuery, limit: 8 });
        setSearchResults((data.items || []) as unknown as SearchResult[]);
        setSearchOpen(true);
      } catch {
        // silent
      } finally {
        setSearchLoading(false);
      }
    }, 280);
    return () => {
      if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    };
  }, [searchQuery]);

  // Close dropdowns on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) {
        setSearchOpen(false);
      }
      if (userMenuRef.current && !userMenuRef.current.contains(e.target as Node)) {
        setUserMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const isRunning = activeJobStatus === "running";
  const isPaused = activeJobStatus === "paused";
  const isActive = isRunning || isPaused;

  const etaLabel = (() => {
    if (!etaSeconds || etaSeconds <= 0) return null;
    if (etaSeconds < 60) return `${Math.round(etaSeconds)}s`;
    return `${Math.round(etaSeconds / 60)}m`;
  })();

  const handleSelectVoter = (voterId: string) => {
    setSearchQuery("");
    setSearchOpen(false);
    setActiveTab("voters" as any);
    // store voter id for profile navigation — we broadcast via a custom event
    window.dispatchEvent(new CustomEvent("vi-mc:open-voter", { detail: { id: voterId } }));
  };

  return (
    <header className="h-14 shrink-0 flex items-center gap-3 px-4 glass border-b border-white/10 dark:border-white/5 z-50 relative">
      {/* Brand — visible on mobile where sidebar is hidden */}
      <div className="flex items-center gap-2 lg:hidden mr-2">
        <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center">
          <Zap className="w-4 h-4 text-white" fill="white" />
        </div>
        <span className="text-sm font-bold tracking-tight">VI-MC</span>
      </div>

      {/* Global Search */}
      <div ref={searchRef} className="relative flex-1 max-w-xl mx-auto lg:mx-0 lg:ml-2">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400 pointer-events-none" />
          <input
            type="text"
            placeholder="Search voters by name, EPIC, house…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-9 py-2 rounded-lg border border-border bg-muted/60 dark:bg-slate-900/80 text-sm placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/50 transition-all"
          />
          {searchLoading && (
            <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400 animate-spin" />
          )}
          {searchQuery && !searchLoading && (
            <button
              onClick={() => { setSearchQuery(""); setSearchOpen(false); }}
              className="absolute right-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400 hover:text-slate-600"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* Search Dropdown */}
        {searchOpen && (
          <div className="absolute top-full left-0 right-0 mt-1.5 card-vimc rounded-xl overflow-hidden z-50 shadow-xl border border-border animate-scale-in">
            {searchResults.length === 0 ? (
              <div className="px-4 py-3 text-sm text-muted-foreground text-center">
                No voters found for "{searchQuery}"
              </div>
            ) : (
              <div>
                <div className="px-3 py-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground border-b border-border bg-muted/40">
                  Voters — {searchResults.length} result{searchResults.length !== 1 ? "s" : ""}
                </div>
                {searchResults.map((v) => (
                  <button
                    key={v.id}
                    onClick={() => handleSelectVoter(v.id)}
                    className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-primary/5 transition-colors text-left"
                  >
                    <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-white font-bold text-xs shrink-0">
                      {(v.name || "?")[0]}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-medium truncate">{v.name || "—"}</div>
                      <div className="text-xs text-muted-foreground font-mono truncate">{v.epic}</div>
                    </div>
                    <div className="text-right shrink-0">
                      <div className="text-xs text-muted-foreground">{v.gender} · {v.age ?? "?"}</div>
                      <div className="text-[10px] text-muted-foreground">{v.house_number}</div>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="flex items-center gap-1.5 ml-auto">
        {/* Job Progress */}
        {isActive && (
          <div className="hidden md:flex items-center gap-2 text-xs px-3 py-1.5 rounded-lg bg-indigo-50 dark:bg-indigo-500/10 border border-indigo-100 dark:border-indigo-500/20 text-indigo-700 dark:text-indigo-300">
            <Loader2 className="w-3 h-3 animate-spin" />
            <span className="font-medium">{Math.round(activeJobProgress ?? 0)}%</span>
            {etaLabel && <span className="text-indigo-400">· {etaLabel}</span>}
            <div className="flex items-center gap-1 ml-1 border-l border-indigo-200 dark:border-indigo-500/30 pl-2">
              {isRunning ? (
                <button onClick={() => void pauseJob()} title="Pause" className="hover:text-indigo-500">
                  <Pause className="w-3 h-3" />
                </button>
              ) : (
                <button onClick={() => void resumeJob()} title="Resume" className="hover:text-indigo-500">
                  <Play className="w-3 h-3" />
                </button>
              )}
              <button onClick={() => void cancelJob()} title="Cancel" className="hover:text-rose-500">
                <XSquare className="w-3 h-3" />
              </button>
            </div>
          </div>
        )}

        {/* AI Assistant button. The assistant is global, so this no longer
            switches tabs on the way to opening it. */}
        <button
          onClick={() => window.dispatchEvent(new CustomEvent("vi-mc:open-ai-assistant"))}
          className="h-8 px-3 rounded-lg bg-gradient-to-r from-indigo-600 via-purple-600 to-rose-600 hover:from-indigo-500 hover:to-rose-500 text-white text-xs font-black shadow-md flex items-center gap-1.5 transition-all"
          title="Ask the AI assistant about the roll"
        >
          <Sparkles className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">AI Assistant</span>
        </button>

        {/* Import button */}
        <button
          onClick={onOpenUpload}
          className="vimc-btn-primary h-8 text-xs"
        >
          <Upload className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">Import PDF</span>
        </button>

        {/* Delete All Data button */}
        <button
          onClick={handleClearDatabase}
          className="h-8 px-2.5 rounded-lg border border-rose-200 dark:border-rose-900/60 bg-rose-50 hover:bg-rose-100 dark:bg-rose-950/40 dark:hover:bg-rose-900/60 text-rose-600 dark:text-rose-400 text-xs font-semibold flex items-center gap-1.5 transition-all shadow-sm"
          title="Delete all data in database"
        >
          <Trash2 className="w-3.5 h-3.5" />
          <span className="hidden md:inline">Delete DB Data</span>
        </button>

        {/* Theme toggle */}
        <button
          onClick={toggleTheme}
          className="h-8 w-8 flex items-center justify-center rounded-lg hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
          title="Toggle theme"
        >
          {theme === "dark" ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
        </button>

        {/* Keyboard shortcuts */}
        <button
          onClick={() => setIsShortcutsOpen(true)}
          className="hidden lg:flex h-8 w-8 items-center justify-center rounded-lg hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
          title="Keyboard shortcuts (?)"
        >
          <Keyboard className="w-4 h-4" />
        </button>

        {/* User menu */}
        <div ref={userMenuRef} className="relative">
          <button
            onClick={() => setUserMenuOpen((v) => !v)}
            className="flex items-center gap-2 h-8 px-2.5 rounded-lg hover:bg-muted transition-colors"
          >
            <div className="w-6 h-6 rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-white text-[10px] font-bold">
              {(authUser?.username || "A")[0].toUpperCase()}
            </div>
            <span className="hidden md:inline text-xs font-medium text-foreground">
              {authUser?.display_name || authUser?.username || "Admin"}
            </span>
            <ChevronDown className="w-3 h-3 text-muted-foreground" />
          </button>

          {userMenuOpen && (
            <div className="absolute right-0 top-full mt-2 w-48 card-vimc rounded-xl shadow-xl border border-border z-50 py-1 animate-scale-in">
              <div className="px-3 py-2 border-b border-border">
                <div className="text-xs font-semibold text-foreground">
                  {authUser?.display_name || authUser?.username}
                </div>
                <div className="text-[11px] text-muted-foreground">Administrator</div>
              </div>
              <button
                onClick={handleClearDatabase}
                className="w-full flex items-center gap-2 px-3 py-2 text-xs font-medium text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-500/10 transition-colors border-b border-border/50"
              >
                <Trash2 className="w-3.5 h-3.5" />
                Delete All Data in DB
              </button>
              <button
                onClick={() => void signOut()}
                className="w-full flex items-center gap-2 px-3 py-2 text-xs text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
              >
                <LogOut className="w-3.5 h-3.5" />
                Sign out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
};

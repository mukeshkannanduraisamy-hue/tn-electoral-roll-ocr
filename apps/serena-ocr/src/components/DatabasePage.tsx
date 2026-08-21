"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";
import {
  Database,
  Table2,
  Search,
  Loader2,
  ChevronLeft,
  ChevronRight,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  Columns3,
  Terminal,
  RefreshCw,
  X,
  Key,
  HardDrive,
  Layers,
  FileDown,
  Play,
  Clock,
  Sparkles,
  CheckCircle2,
  AlertCircle,
  AlertTriangle,
  Trash2,
  Eye,
  Hash,
  Type,
  User,
  Home,
  MapPin,
  Calendar,
  Filter,
  Copy,
  Check,
  Download,
  Share2,
  ExternalLink,
  ShieldCheck,
  Grid,
} from "lucide-react";
import {
  fetchTables,
  fetchColumns,
  fetchRows,
  fetchIndexes,
  fetchDbStats,
  executeQuery,
  downloadCsv,
  promoteAllToDb,
  truncateTable,
  truncateAllTables,
  type DbTableInfo,
  type DbColumn,
  type DbIndex,
  type DbRowsResponse,
  type DbQueryResult,
  type DbStats,
} from "@/lib/databaseApi";
import { useSerenaStore } from "@/store/useSerenaStore";
import { toast } from "sonner";

export const DatabasePage: React.FC = () => {
  const { theme } = useSerenaStore();

  // Database Meta State
  const [stats, setStats] = useState<DbStats | null>(null);
  const [tables, setTables] = useState<DbTableInfo[]>([]);
  const [selectedTable, setSelectedTable] = useState<string>("view_voters_list");
  const [viewFilterMode, setViewFilterMode] = useState<"views_only" | "all">("views_only");
  const [isLoadingTables, setIsLoadingTables] = useState(true);

  // Table Rows State
  const [rowsData, setRowsData] = useState<DbRowsResponse | null>(null);
  const [columns, setColumns] = useState<DbColumn[]>([]);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [searchQuery, setSearchQuery] = useState("");
  const [genderFilter, setGenderFilter] = useState<"all" | "male" | "female">("all");
  const [ageGroupFilter, setAgeGroupFilter] = useState<"all" | "18-30" | "31-50" | "50+">("all");
  const [sortCol, setSortCol] = useState<string | undefined>(undefined);
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("asc");
  const [isLoadingRows, setIsLoadingRows] = useState(false);
  const [hiddenCols, setHiddenCols] = useState<Set<string>>(new Set(["raw_ocr_json", "extra_json", "bbox_json", "voters_list_id", "part_details_id", "elector_counts_id"]));
  const [showColSelector, setShowColSelector] = useState(false);

  // Voter Detail Card Modal
  const [selectedRowDetail, setSelectedRowDetail] = useState<Record<string, any> | null>(null);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  // SQL Console State
  const [showSqlDrawer, setShowSqlDrawer] = useState(false);
  const [sqlQuery, setSqlQuery] = useState("SELECT * FROM view_voters_list LIMIT 50;");
  const [queryResult, setQueryResult] = useState<DbQueryResult | null>(null);
  const [isExecutingSql, setIsExecutingSql] = useState(false);
  const [sqlError, setSqlError] = useState<string | null>(null);

  // Truncate & Promote State
  const [confirmTruncate, setConfirmTruncate] = useState<"all" | string | null>(null);
  const [isTruncating, setIsTruncating] = useState(false);
  const [isPromotingAll, setIsPromotingAll] = useState(false);

  // Filter Tables / Views
  const displayedTables = useMemo(() => {
    if (viewFilterMode === "views_only") {
      const views = tables.filter((t) => t.type === "view" || t.name.startsWith("view_"));
      return views.length > 0 ? views : tables;
    }
    return tables;
  }, [tables, viewFilterMode]);

  // Handle Truncate Execution
  const handleExecuteTruncate = async () => {
    if (!confirmTruncate) return;
    setIsTruncating(true);
    try {
      if (confirmTruncate === "all") {
        await truncateAllTables();
        toast.success("Entire database truncated successfully!");
      } else {
        await truncateTable(confirmTruncate);
        toast.success(`Table "${confirmTruncate}" truncated successfully!`);
      }
      setConfirmTruncate(null);
      void loadOverview();
      void loadTableDetails();
    } catch (e: any) {
      toast.error(e?.message || "Truncate operation failed");
    } finally {
      setIsTruncating(false);
    }
  };

  // Promote OCR Records to DB
  const handlePromoteAll = async () => {
    setIsPromotingAll(true);
    toast.info("Promoting extracted OCR records to voters database...");
    try {
      const res = await promoteAllToDb();
      toast.success(`Promoted! Created: ${res.created}, Updated: ${res.updated}, Skipped: ${res.skipped}`);
      void loadOverview();
      void loadTableDetails();
    } catch (e: any) {
      toast.error(e?.message || "Failed to promote records");
    } finally {
      setIsPromotingAll(false);
    }
  };

  // Load Database Overview & Tables
  const loadOverview = useCallback(async () => {
    setIsLoadingTables(true);
    try {
      const [st, tbls] = await Promise.all([fetchDbStats(), fetchTables()]);
      setStats(st);
      setTables(tbls);

      // Default to view_voters_list if present, or first view
      const viewList = tbls.filter((t) => t.type === "view" || t.name.startsWith("view_"));
      if (viewList.some((t) => t.name === "view_voters_list")) {
        setSelectedTable("view_voters_list");
      } else if (viewList.length > 0) {
        setSelectedTable(viewList[0].name);
      } else if (tbls.length > 0 && !tbls.some((t) => t.name === selectedTable)) {
        setSelectedTable(tbls[0].name);
      }
    } catch (e: any) {
      toast.error(e?.message || "Failed to load database overview");
    } finally {
      setIsLoadingTables(false);
    }
  }, []);

  useEffect(() => {
    void loadOverview();
  }, [loadOverview]);

  // Load Table Rows & Schema
  const loadTableDetails = useCallback(async () => {
    if (!selectedTable) return;
    setIsLoadingRows(true);
    try {
      const [cols, rows] = await Promise.all([
        fetchColumns(selectedTable),
        fetchRows(selectedTable, page, pageSize, searchQuery || undefined, sortCol, sortOrder),
      ]);
      setColumns(cols);
      setRowsData(rows);
    } catch (e: any) {
      toast.error(e?.message || `Failed to fetch data for ${selectedTable}`);
    } finally {
      setIsLoadingRows(false);
    }
  }, [selectedTable, page, pageSize, searchQuery, sortCol, sortOrder]);

  useEffect(() => {
    void loadTableDetails();
  }, [loadTableDetails]);

  // Client-Side Quick Filters (Gender & Age)
  const displayRows = useMemo(() => {
    if (!rowsData?.rows) return [];
    let rows = rowsData.rows;

    if (selectedTable === "voters") {
      if (genderFilter === "male") {
        rows = rows.filter((r) => String(r.gender || "").toLowerCase().includes("male") || String(r.gender || "").includes("ஆண்"));
      } else if (genderFilter === "female") {
        rows = rows.filter((r) => String(r.gender || "").toLowerCase().includes("female") || String(r.gender || "").includes("பெண்"));
      }

      if (ageGroupFilter === "18-30") {
        rows = rows.filter((r) => Number(r.age) >= 18 && Number(r.age) <= 30);
      } else if (ageGroupFilter === "31-50") {
        rows = rows.filter((r) => Number(r.age) >= 31 && Number(r.age) <= 50);
      } else if (ageGroupFilter === "50+") {
        rows = rows.filter((r) => Number(r.age) > 50);
      }
    }

    return rows;
  }, [rowsData, selectedTable, genderFilter, ageGroupFilter]);

  // Handle Sort
  const handleSort = (colName: string) => {
    if (sortCol === colName) {
      if (sortOrder === "asc") setSortOrder("desc");
      else {
        setSortCol(undefined);
        setSortOrder("asc");
      }
    } else {
      setSortCol(colName);
      setSortOrder("asc");
    }
  };

  // Toggle Column Visibility
  const toggleColumn = (colName: string) => {
    setHiddenCols((prev) => {
      const next = new Set(prev);
      if (next.has(colName)) next.delete(colName);
      else next.add(colName);
      return next;
    });
  };

  // Copy helper
  const handleCopy = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    toast.success("Copied to clipboard!");
    setTimeout(() => setCopiedKey(null), 2000);
  };

  // Execute Custom SQL
  const handleRunSql = async () => {
    if (!sqlQuery.trim()) return;
    setIsExecutingSql(true);
    setSqlError(null);
    try {
      const res = await executeQuery(sqlQuery);
      setQueryResult(res);
      toast.success(`Query executed: ${res.row_count} row(s) returned`);
    } catch (e: any) {
      setSqlError(e?.message || "Query execution failed");
      toast.error("SQL execution error");
    } finally {
      setIsExecutingSql(false);
    }
  };

  const visibleColumns = columns.filter((c) => !hiddenCols.has(c.name));

  return (
    <div className="flex flex-col h-full w-full bg-[#F9F9F9] dark:bg-[#1E1E1E] text-slate-800 dark:text-slate-100 font-sans select-none antialiased overflow-hidden">
      {/* ========================================================================= */}
      {/* 1. TOP SUMMARY CARDS & STATS BAR */}
      {/* ========================================================================= */}
      <div className="px-4 py-2.5 bg-white dark:bg-[#202020] border-b border-slate-200 dark:border-white/10 flex items-center justify-between gap-4 shrink-0 flex-wrap shadow-2xs">
        {/* Left Views vs All Tables Switcher & Tabs */}
        <div className="flex items-center gap-2 overflow-x-auto py-0.5 max-w-full">
          {/* Mode Pill Toggle */}
          <div className="flex items-center bg-slate-200/70 dark:bg-white/5 p-0.5 rounded-lg border border-slate-300 dark:border-white/10 shrink-0">
            <button
              onClick={() => {
                setViewFilterMode("views_only");
                const views = tables.filter((t) => t.type === "view" || t.name.startsWith("view_"));
                if (views.length > 0 && !views.some((v) => v.name === selectedTable)) {
                  setSelectedTable(views[0].name);
                }
              }}
              className={`px-2.5 py-1 rounded-md text-[11px] font-bold flex items-center gap-1.5 transition-all ${
                viewFilterMode === "views_only"
                  ? "bg-[#005FB8] text-white shadow-xs"
                  : "text-slate-600 dark:text-slate-400 hover:text-slate-900"
              }`}
            >
              <Eye className="w-3.5 h-3.5" />
              <span>Views Only</span>
            </button>
            <button
              onClick={() => setViewFilterMode("all")}
              className={`px-2.5 py-1 rounded-md text-[11px] font-medium flex items-center gap-1.5 transition-all ${
                viewFilterMode === "all"
                  ? "bg-[#005FB8] text-white shadow-xs"
                  : "text-slate-600 dark:text-slate-400 hover:text-slate-900"
              }`}
            >
              <Table2 className="w-3.5 h-3.5" />
              <span>All Tables</span>
            </button>
          </div>

          <div className="h-5 w-[1px] bg-slate-300 dark:bg-white/10 mx-0.5 shrink-0" />

          {/* Table / View Tabs */}
          {displayedTables.map((t) => {
            const isSelected = t.name === selectedTable;
            const isView = t.type === "view" || t.name.startsWith("view_");
            return (
              <button
                key={t.name}
                onClick={() => {
                  setSelectedTable(t.name);
                  setPage(1);
                  setSearchQuery("");
                }}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-2 transition-all shrink-0 ${
                  isSelected
                    ? "bg-[#005FB8] text-white shadow-xs"
                    : "bg-slate-100 dark:bg-white/5 hover:bg-slate-200 dark:hover:bg-white/10 text-slate-700 dark:text-slate-300"
                }`}
              >
                {isView ? <Eye className="w-3.5 h-3.5 text-cyan-400" /> : <Table2 className="w-3.5 h-3.5 text-amber-500" />}
                <span>{t.name}</span>
                <span
                  className={`px-1.5 py-0.2 rounded-full text-[10px] font-mono ${
                    isSelected
                      ? "bg-white/20 text-white"
                      : "bg-black/5 dark:bg-white/10 text-slate-500 dark:text-slate-400"
                  }`}
                >
                  {t.row_count.toLocaleString()}
                </span>
              </button>
            );
          })}
        </div>

        {/* Right Action Buttons */}
        <div className="flex items-center gap-2 shrink-0">
          {/* Promote OCR to DB */}
          <button
            onClick={() => void handlePromoteAll()}
            disabled={isPromotingAll}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold shadow-xs disabled:opacity-50 transition-all"
            title="Sync extracted OCR records into curated database"
          >
            <Sparkles className={`w-3.5 h-3.5 ${isPromotingAll ? "animate-spin" : ""}`} />
            <span>Sync OCR ➔ DB</span>
          </button>

          {/* Export CSV */}
          <button
            onClick={() =>
              downloadCsv(
                `${selectedTable}.csv`,
                visibleColumns.map((c) => c.name),
                displayRows
              )
            }
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md bg-slate-100 dark:bg-white/10 hover:bg-slate-200 dark:hover:bg-white/15 text-slate-700 dark:text-slate-300 text-xs font-medium transition-all"
            title="Download CSV"
          >
            <Download className="w-3.5 h-3.5 text-blue-500" />
            <span>Export CSV</span>
          </button>

          {/* Truncate Current Table */}
          <button
            onClick={() => setConfirmTruncate(selectedTable)}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md bg-red-500/10 hover:bg-red-500/20 text-red-600 dark:text-red-400 text-xs font-medium transition-all border border-red-500/20"
            title={`Clear all records in ${selectedTable}`}
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span>Truncate Table</span>
          </button>

          {/* Refresh */}
          <button
            onClick={() => void loadTableDetails()}
            className="p-1.5 rounded-md bg-slate-100 dark:bg-white/10 hover:bg-slate-200 dark:hover:bg-white/15 text-slate-600 dark:text-slate-300"
            title="Refresh Table (F5)"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoadingRows ? "animate-spin" : ""}`} />
          </button>

          {/* SQL Console Toggle */}
          <button
            onClick={() => setShowSqlDrawer(!showSqlDrawer)}
            className={`flex items-center gap-1 px-2.5 py-1.5 rounded-md text-xs font-medium transition-all ${
              showSqlDrawer
                ? "bg-purple-600 text-white"
                : "bg-slate-100 dark:bg-white/10 text-slate-700 dark:text-slate-300 hover:bg-slate-200"
            }`}
          >
            <Terminal className="w-3.5 h-3.5" />
            <span>SQL</span>
          </button>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* 2. COMMAND & FILTER BAR */}
      {/* ========================================================================= */}
      <div className="px-4 py-2 bg-[#F3F3F3] dark:bg-[#252525] border-b border-slate-200 dark:border-white/10 flex items-center justify-between gap-3 shrink-0 text-xs flex-wrap">
        {/* Search Bar */}
        <div className="flex items-center gap-2 flex-1 min-w-[240px] max-w-md">
          <div className="w-full flex items-center bg-white dark:bg-[#1E1E1E] border border-slate-300 dark:border-white/10 rounded-md px-2.5 py-1.5 shadow-2xs focus-within:ring-1 focus-within:ring-blue-500">
            <Search className="w-3.5 h-3.5 text-slate-400 mr-2 shrink-0" />
            <input
              type="text"
              placeholder={`Search ${selectedTable} (Name, EPIC, House No, Section...)`}
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setPage(1);
              }}
              className="w-full bg-transparent text-xs text-slate-900 dark:text-white placeholder:text-slate-400 focus:outline-none"
            />
            {searchQuery && (
              <button onClick={() => setSearchQuery("")} className="text-slate-400 hover:text-slate-600">
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>

        {/* Quick Filter Chips (for Voters table) */}
        {selectedTable === "voters" && (
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-[11px] text-slate-400 flex items-center gap-1 font-medium">
              <Filter className="w-3 h-3" /> Filter:
            </span>

            {/* Gender Filters */}
            <div className="flex items-center bg-slate-200/70 dark:bg-white/5 p-0.5 rounded-md border border-slate-300 dark:border-white/10">
              <button
                onClick={() => setGenderFilter("all")}
                className={`px-2 py-0.5 rounded text-[11px] font-medium transition-all ${
                  genderFilter === "all" ? "bg-white dark:bg-white/15 text-blue-600 dark:text-blue-400 shadow-2xs font-bold" : "text-slate-600 dark:text-slate-400"
                }`}
              >
                All
              </button>
              <button
                onClick={() => setGenderFilter("male")}
                className={`px-2 py-0.5 rounded text-[11px] font-medium transition-all ${
                  genderFilter === "male" ? "bg-white dark:bg-white/15 text-blue-600 dark:text-blue-400 shadow-2xs font-bold" : "text-slate-600 dark:text-slate-400"
                }`}
              >
                👨 Male
              </button>
              <button
                onClick={() => setGenderFilter("female")}
                className={`px-2 py-0.5 rounded text-[11px] font-medium transition-all ${
                  genderFilter === "female" ? "bg-white dark:bg-white/15 text-blue-600 dark:text-blue-400 shadow-2xs font-bold" : "text-slate-600 dark:text-slate-400"
                }`}
              >
                👩 Female
              </button>
            </div>

            {/* Age Group Filters */}
            <div className="flex items-center bg-slate-200/70 dark:bg-white/5 p-0.5 rounded-md border border-slate-300 dark:border-white/10">
              <button
                onClick={() => setAgeGroupFilter("all")}
                className={`px-2 py-0.5 rounded text-[11px] font-medium transition-all ${
                  ageGroupFilter === "all" ? "bg-white dark:bg-white/15 text-blue-600 dark:text-blue-400 shadow-2xs font-bold" : "text-slate-600 dark:text-slate-400"
                }`}
              >
                All Ages
              </button>
              <button
                onClick={() => setAgeGroupFilter("18-30")}
                className={`px-2 py-0.5 rounded text-[11px] font-medium transition-all ${
                  ageGroupFilter === "18-30" ? "bg-white dark:bg-white/15 text-blue-600 dark:text-blue-400 shadow-2xs font-bold" : "text-slate-600 dark:text-slate-400"
                }`}
              >
                18-30
              </button>
              <button
                onClick={() => setAgeGroupFilter("31-50")}
                className={`px-2 py-0.5 rounded text-[11px] font-medium transition-all ${
                  ageGroupFilter === "31-50" ? "bg-white dark:bg-white/15 text-blue-600 dark:text-blue-400 shadow-2xs font-bold" : "text-slate-600 dark:text-slate-400"
                }`}
              >
                31-50
              </button>
              <button
                onClick={() => setAgeGroupFilter("50+")}
                className={`px-2 py-0.5 rounded text-[11px] font-medium transition-all ${
                  ageGroupFilter === "50+" ? "bg-white dark:bg-white/15 text-blue-600 dark:text-blue-400 shadow-2xs font-bold" : "text-slate-600 dark:text-slate-400"
                }`}
              >
                50+
              </button>
            </div>
          </div>
        )}

        {/* Columns Visibility Dropdown */}
        <div className="relative">
          <button
            onClick={() => setShowColSelector(!showColSelector)}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border border-slate-300 dark:border-white/10 bg-white dark:bg-[#1E1E1E] text-slate-700 dark:text-slate-300 hover:bg-slate-50 text-xs shadow-2xs"
          >
            <Columns3 className="w-3.5 h-3.5 text-slate-500" />
            <span>Columns ({visibleColumns.length}/{columns.length})</span>
          </button>

          {showColSelector && (
            <div className="absolute right-0 mt-1 w-56 bg-white dark:bg-[#252525] rounded-lg shadow-xl border border-slate-300 dark:border-white/15 p-2 z-50 max-h-72 overflow-y-auto">
              <div className="text-[11px] font-bold text-slate-500 dark:text-slate-400 px-2 py-1 border-b border-slate-200 dark:border-white/10 mb-1 flex justify-between">
                <span>Toggle Columns</span>
                <button onClick={() => setShowColSelector(false)} className="text-slate-400 hover:text-slate-600">
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
              <div className="space-y-0.5">
                {columns.map((c) => {
                  const isVisible = !hiddenCols.has(c.name);
                  return (
                    <label
                      key={c.name}
                      onClick={() => toggleColumn(c.name)}
                      className="flex items-center gap-2 px-2 py-1 rounded hover:bg-slate-100 dark:hover:bg-white/5 cursor-pointer text-xs"
                    >
                      <input type="checkbox" checked={isVisible} onChange={() => {}} className="rounded text-blue-600" />
                      <span className="truncate">{c.name}</span>
                    </label>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ========================================================================= */}
      {/* 3. SQL DRAWER (COLLAPSIBLE) */}
      {/* ========================================================================= */}
      {showSqlDrawer && (
        <div className="bg-[#1C1C1C] text-white p-3 border-b border-slate-700 flex flex-col gap-2 shrink-0 animate-in slide-in-from-top-2 duration-150">
          <div className="flex items-center justify-between text-xs">
            <span className="font-mono font-bold text-purple-400 flex items-center gap-1.5">
              <Terminal className="w-3.5 h-3.5" /> SQL Query Console
            </span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setSqlQuery("SELECT gender, count(*) FROM voters GROUP BY gender;")}
                className="text-[10px] text-slate-400 hover:text-white underline font-mono"
              >
                Sample: Gender Count
              </button>
              <button
                onClick={() => setSqlQuery("SELECT section_name, count(*) FROM voters GROUP BY section_name;")}
                className="text-[10px] text-slate-400 hover:text-white underline font-mono"
              >
                Sample: Section Summary
              </button>
              <button onClick={() => setShowSqlDrawer(false)} className="text-slate-400 hover:text-white">
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          <div className="flex gap-2">
            <textarea
              value={sqlQuery}
              onChange={(e) => setSqlQuery(e.target.value)}
              rows={2}
              className="flex-1 bg-[#121212] border border-slate-700 rounded-md p-2 text-xs font-mono text-emerald-400 focus:outline-none focus:border-purple-500"
            />
            <button
              onClick={() => void handleRunSql()}
              disabled={isExecutingSql}
              className="px-4 bg-purple-600 hover:bg-purple-700 font-semibold text-xs rounded-md flex items-center gap-1.5 transition-all shadow-xs disabled:opacity-50"
            >
              <Play className="w-3.5 h-3.5 fill-white" />
              <span>Run</span>
            </button>
          </div>

          {sqlError && (
            <div className="text-[11px] font-mono text-red-400 bg-red-950/40 p-1.5 rounded border border-red-800">
              {sqlError}
            </div>
          )}

          {queryResult && (
            <div className="text-[11px] font-mono text-slate-300 max-h-36 overflow-y-auto bg-[#121212] p-2 rounded border border-slate-800">
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-slate-700 text-purple-300">
                    {queryResult.columns.map((c) => (
                      <th key={c} className="p-1">{c}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {queryResult.rows.map((r, idx) => (
                    <tr key={idx} className="border-b border-slate-800/50 hover:bg-white/5">
                      {queryResult.columns.map((c) => (
                        <td key={c} className="p-1">{String(r[c] ?? "—")}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ========================================================================= */}
      {/* 4. MAIN DATA GRID (EXCEL / FLUID TABLE VIEW) */}
      {/* ========================================================================= */}
      <div className="flex-1 min-h-0 overflow-auto bg-white dark:bg-[#181818] relative">
        {isLoadingRows ? (
          <div className="flex flex-col items-center justify-center h-full text-slate-400 gap-2 p-8">
            <Loader2 className="w-8 h-8 animate-spin text-[#005FB8]" />
            <span className="text-xs font-semibold">Loading {selectedTable} data…</span>
          </div>
        ) : displayRows.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-slate-400 gap-2 p-8 text-center">
            <Table2 className="w-12 h-12 text-slate-300 dark:text-slate-700" />
            <div className="text-xs font-bold text-slate-700 dark:text-slate-300">No records found</div>
            <p className="text-[11px] text-slate-500">
              {searchQuery ? "Try refining your search query" : "Run OCR processing or click 'Sync OCR ➔ DB' to populate records"}
            </p>
          </div>
        ) : (
          <table className="w-full text-left text-xs border-collapse font-sans">
            <thead className="bg-[#F8F9FA] dark:bg-[#202020] border-b border-slate-200 dark:border-white/10 text-slate-600 dark:text-slate-400 font-semibold sticky top-0 z-10 select-none shadow-2xs">
              <tr>
                <th className="w-10 px-3 py-2 text-center text-slate-400">#</th>
                {visibleColumns.map((col) => {
                  const isSorted = sortCol === col.name;
                  return (
                    <th
                      key={col.name}
                      onClick={() => handleSort(col.name)}
                      className="px-3 py-2 cursor-pointer hover:bg-slate-200/50 dark:hover:bg-white/5 transition-colors whitespace-nowrap"
                    >
                      <div className="flex items-center gap-1.5">
                        <span className="truncate">{col.name}</span>
                        {isSorted ? (
                          sortOrder === "asc" ? (
                            <ArrowUp className="w-3 h-3 text-blue-600" />
                          ) : (
                            <ArrowDown className="w-3 h-3 text-blue-600" />
                          )
                        ) : (
                          <ArrowUpDown className="w-3 h-3 text-slate-300 dark:text-slate-600 opacity-60" />
                        )}
                      </div>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-white/5">
              {displayRows.map((row, rIdx) => (
                <tr
                  key={String(row.id ?? rIdx)}
                  onClick={() => setSelectedRowDetail(row)}
                  className="hover:bg-[#E5F3FF] dark:hover:bg-[#003774]/30 cursor-pointer transition-colors group"
                >
                  <td className="px-3 py-2 text-center font-mono text-[11px] text-slate-400 group-hover:text-blue-600">
                    {(page - 1) * pageSize + rIdx + 1}
                  </td>
                  {visibleColumns.map((col) => {
                    const val = row[col.name];
                    const isEpic = col.name === "epic_id";
                    const isName = col.name === "name_ta" || col.name === "name_en";
                    const isGender = col.name === "gender";

                    return (
                      <td key={col.name} className="px-3 py-2 whitespace-nowrap max-w-xs truncate">
                        {isEpic ? (
                          <span className="font-mono font-bold text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-500/10 px-1.5 py-0.5 rounded border border-blue-200 dark:border-blue-500/20">
                            {String(val || "—")}
                          </span>
                        ) : isName ? (
                          <span className="font-medium text-slate-900 dark:text-white">
                            {String(val || "—")}
                          </span>
                        ) : isGender ? (
                          <span
                            className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                              String(val).toLowerCase().includes("female") || String(val).includes("பெண்")
                                ? "bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20"
                                : "bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20"
                            }`}
                          >
                            {String(val || "—")}
                          </span>
                        ) : (
                          <span className="text-slate-700 dark:text-slate-300">
                            {String(val ?? "—")}
                          </span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* ========================================================================= */}
      {/* 5. WINDOWS 11 BOTTOM PAGINATION BAR */}
      {/* ========================================================================= */}
      {(() => {
        const totalRows = rowsData?.total || 0;
        const totalPages = Math.ceil(totalRows / pageSize) || 1;
        return (
          <div className="h-9 px-4 bg-[#EAEAEA] dark:bg-[#202020] border-t border-slate-300 dark:border-white/10 flex items-center justify-between text-xs text-slate-600 dark:text-slate-400 shrink-0 select-none">
            {/* Total Records Status */}
            <div className="flex items-center gap-3">
              <span>
                Showing <strong className="text-slate-900 dark:text-white">{displayRows.length}</strong> of{" "}
                <strong className="text-slate-900 dark:text-white">{totalRows.toLocaleString()}</strong> rows
              </span>
              <span className="text-slate-300 dark:text-slate-600">|</span>
              <span>Table: <strong className="text-slate-900 dark:text-white">{selectedTable}</strong></span>
            </div>

            {/* Page Controls */}
            <div className="flex items-center gap-2">
              {/* Page Size Selector */}
              <div className="flex items-center gap-1">
                <span className="text-[11px] text-slate-400">Rows per page:</span>
                <select
                  value={pageSize}
                  onChange={(e) => {
                    setPageSize(Number(e.target.value));
                    setPage(1);
                  }}
                  className="bg-white dark:bg-[#1E1E1E] border border-slate-300 dark:border-white/10 rounded px-1.5 py-0.5 text-xs focus:outline-none cursor-pointer"
                >
                  <option value={25}>25</option>
                  <option value={50}>50</option>
                  <option value={100}>100</option>
                  <option value={250}>250</option>
                </select>
              </div>

              <div className="h-4 w-[1px] bg-slate-300 dark:bg-white/10 mx-1" />

              {/* Navigation Arrows */}
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="p-1 rounded hover:bg-slate-200 dark:hover:bg-white/10 disabled:opacity-30 transition-colors"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>

              <span className="font-mono text-xs">
                Page <strong className="text-slate-900 dark:text-white">{page}</strong> of{" "}
                <strong>{totalPages}</strong>
              </span>

              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="p-1 rounded hover:bg-slate-200 dark:hover:bg-white/10 disabled:opacity-30 transition-colors"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        );
      })()}

      {/* ========================================================================= */}
      {/* 6. VOTER / ROW DETAILS MODAL (RICH USER CARD) */}
      {/* ========================================================================= */}
      {selectedRowDetail && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-xs flex items-center justify-center p-4 z-50 animate-in fade-in duration-150">
          <div className="bg-white dark:bg-[#252525] rounded-xl shadow-2xl border border-slate-300 dark:border-white/15 w-full max-w-lg overflow-hidden flex flex-col max-h-[85vh]">
            {/* Header */}
            <div className="px-5 py-3.5 bg-[#F8F9FA] dark:bg-[#1E1E1E] border-b border-slate-200 dark:border-white/10 flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-blue-600/10 border border-blue-600/20 flex items-center justify-center text-blue-600 dark:text-blue-400">
                  <User className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-xs font-bold text-slate-900 dark:text-white">
                    {selectedRowDetail.name_ta || selectedRowDetail.name_en || selectedRowDetail.name || "Record Details"}
                  </h3>
                  <span className="text-[10px] text-slate-400 font-mono">
                    Table: {selectedTable} · ID: {selectedRowDetail.id || "—"}
                  </span>
                </div>
              </div>

              <button
                onClick={() => setSelectedRowDetail(null)}
                className="w-7 h-7 rounded-lg hover:bg-slate-200 dark:hover:bg-white/10 flex items-center justify-center text-slate-400 hover:text-slate-600 dark:hover:text-white transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Body */}
            <div className="p-5 overflow-y-auto space-y-4">
              {/* Top Highlights (for Voters) */}
              {selectedTable === "voters" && (
                <div className="grid grid-cols-2 gap-2.5 p-3 rounded-lg bg-slate-50 dark:bg-[#1E1E1E] border border-slate-200 dark:border-white/10 font-mono text-xs">
                  <div>
                    <span className="text-[10px] text-slate-400">EPIC Number</span>
                    <div className="font-bold text-blue-600 dark:text-blue-400 flex items-center gap-1.5 mt-0.5">
                      <span>{selectedRowDetail.epic_id || "—"}</span>
                      {selectedRowDetail.epic_id && (
                        <button
                          onClick={() => handleCopy(selectedRowDetail.epic_id, "epic")}
                          className="text-slate-400 hover:text-blue-600"
                        >
                          {copiedKey === "epic" ? <Check className="w-3 h-3 text-emerald-500" /> : <Copy className="w-3 h-3" />}
                        </button>
                      )}
                    </div>
                  </div>

                  <div>
                    <span className="text-[10px] text-slate-400">Gender / Age</span>
                    <div className="font-bold text-slate-800 dark:text-slate-200 mt-0.5">
                      {selectedRowDetail.gender || "—"} · {selectedRowDetail.age ? `${selectedRowDetail.age} yrs` : "—"}
                    </div>
                  </div>

                  <div>
                    <span className="text-[10px] text-slate-400">House No</span>
                    <div className="font-bold text-slate-800 dark:text-slate-200 mt-0.5 truncate">
                      {selectedRowDetail.house_no || "—"}
                    </div>
                  </div>

                  <div>
                    <span className="text-[10px] text-slate-400">Section</span>
                    <div className="font-bold text-slate-800 dark:text-slate-200 mt-0.5 truncate">
                      {selectedRowDetail.section_name || "—"}
                    </div>
                  </div>
                </div>
              )}

              {/* Complete Property Key-Value List */}
              <div className="space-y-1.5">
                <span className="text-[11px] font-bold text-slate-500 dark:text-slate-400">All Attributes</span>
                <div className="divide-y divide-slate-100 dark:divide-white/5 border border-slate-200 dark:border-white/10 rounded-lg overflow-hidden bg-white dark:bg-[#1E1E1E]">
                  {Object.entries(selectedRowDetail).map(([k, v]) => (
                    <div key={k} className="flex justify-between items-center px-3 py-2 text-xs hover:bg-slate-50 dark:hover:bg-white/5">
                      <span className="font-mono text-slate-400 text-[11px] truncate max-w-[140px]">{k}:</span>
                      <span className="font-mono text-slate-800 dark:text-slate-200 truncate max-w-[280px] text-right font-medium">
                        {String(v ?? "—")}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Footer */}
            <div className="px-5 py-3 bg-[#F8F9FA] dark:bg-[#1E1E1E] border-t border-slate-200 dark:border-white/10 flex justify-between items-center">
              <button
                onClick={() => handleCopy(JSON.stringify(selectedRowDetail, null, 2), "json")}
                className="px-3 py-1.5 rounded-md border border-slate-300 dark:border-white/10 text-xs font-semibold text-slate-700 dark:text-slate-300 hover:bg-slate-100 flex items-center gap-1.5"
              >
                {copiedKey === "json" ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
                <span>Copy JSON</span>
              </button>

              <button
                onClick={() => setSelectedRowDetail(null)}
                className="px-4 py-1.5 rounded-md bg-[#005FB8] hover:bg-[#004E98] text-white text-xs font-semibold"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 7. CONFIRM TRUNCATE DIALOG */}
      {/* ========================================================================= */}
      {confirmTruncate && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4 z-50 animate-in fade-in duration-150">
          <div className="bg-white dark:bg-[#252525] rounded-xl shadow-2xl border border-red-500/30 w-full max-w-md p-5 space-y-4">
            <div className="flex items-center gap-3 text-red-600 dark:text-red-400">
              <div className="w-10 h-10 rounded-lg bg-red-500/10 border border-red-500/20 flex items-center justify-center">
                <AlertTriangle className="w-5 h-5" />
              </div>
              <div>
                <h3 className="font-bold text-sm text-slate-900 dark:text-white">
                  Confirm Truncate Table
                </h3>
                <p className="text-xs text-slate-500">
                  Are you sure you want to clear all data in <strong className="text-red-500 font-mono">{confirmTruncate}</strong>?
                </p>
                {confirmTruncate.startsWith("view_") && (
                  <p className="text-[11px] text-blue-600 dark:text-blue-400 font-medium">
                    ℹ️ This will truncate the underlying data table (<strong>{confirmTruncate === "view_voters_list" ? "voters" : "polling_stations"}</strong>).
                  </p>
                )}
              </div>
            </div>

            <p className="text-xs text-slate-600 dark:text-slate-400 bg-red-50 dark:bg-red-950/30 p-3 rounded-lg border border-red-200 dark:border-red-900/50">
              ⚠️ This operation will permanently remove all rows from this table. This action cannot be undone.
            </p>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                onClick={() => setConfirmTruncate(null)}
                disabled={isTruncating}
                className="px-3 py-1.5 rounded-md border border-slate-300 dark:border-white/10 text-xs font-semibold text-slate-700 dark:text-slate-300 hover:bg-slate-100"
              >
                Cancel
              </button>
              <button
                onClick={() => void handleExecuteTruncate()}
                disabled={isTruncating}
                className="px-4 py-1.5 rounded-md bg-red-600 hover:bg-red-700 text-white text-xs font-semibold flex items-center gap-1.5 shadow-xs"
              >
                {isTruncating && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                <span>Yes, Truncate Now</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

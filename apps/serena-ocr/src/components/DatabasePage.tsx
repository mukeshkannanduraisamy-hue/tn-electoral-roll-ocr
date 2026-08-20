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
  const [selectedTable, setSelectedTable] = useState<string>("voters");
  const [activeTab, setActiveTab] = useState<"rows" | "columns" | "sql">("rows");
  const [isLoadingTables, setIsLoadingTables] = useState(true);

  // Table Rows State
  const [rowsData, setRowsData] = useState<DbRowsResponse | null>(null);
  const [columns, setColumns] = useState<DbColumn[]>([]);
  const [indexes, setIndexes] = useState<DbIndex[]>([]);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [searchQuery, setSearchQuery] = useState("");
  const [sortCol, setSortCol] = useState<string | undefined>(undefined);
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("asc");
  const [isLoadingRows, setIsLoadingRows] = useState(false);

  // SQL Console State
  const [sqlQuery, setSqlQuery] = useState("SELECT * FROM voters LIMIT 50;");
  const [queryResult, setQueryResult] = useState<DbQueryResult | null>(null);
  const [isExecutingSql, setIsExecutingSql] = useState(false);
  const [sqlError, setSqlError] = useState<string | null>(null);

  // Modal Detail State
  const [modalValue, setModalValue] = useState<{ title: string; content: string } | null>(null);
  const [isPromotingAll, setIsPromotingAll] = useState(false);
  const [confirmTruncate, setConfirmTruncate] = useState<"all" | string | null>(null);
  const [isTruncating, setIsTruncating] = useState(false);

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

  // Load Database Overview & Tables
  const loadOverview = useCallback(async () => {
    setIsLoadingTables(true);
    try {
      const [st, tbls] = await Promise.all([fetchDbStats(), fetchTables()]);
      setStats(st);
      setTables(tbls);
      if (tbls.length > 0 && !tbls.some((t) => t.name === selectedTable)) {
        setSelectedTable(tbls[0].name);
      }
    } catch (e: any) {
      toast.error(e?.message || "Failed to load database overview");
    } finally {
      setIsLoadingTables(false);
    }
  }, [selectedTable]);

  useEffect(() => {
    void loadOverview();
  }, [loadOverview]);

  // Load Table Rows & Schema when table or filter changes
  const loadTableDetails = useCallback(async () => {
    if (!selectedTable) return;
    setIsLoadingRows(true);
    try {
      const [cols, idxs, rows] = await Promise.all([
        fetchColumns(selectedTable),
        fetchIndexes(selectedTable).catch(() => []),
        fetchRows(selectedTable, page, pageSize, searchQuery || undefined, sortCol, sortOrder),
      ]);
      setColumns(cols);
      setIndexes(idxs);
      setRowsData(rows);
    } catch (e: any) {
      toast.error(`Error loading table ${selectedTable}: ${e?.message}`);
    } finally {
      setIsLoadingRows(false);
    }
  }, [selectedTable, page, pageSize, searchQuery, sortCol, sortOrder]);

  useEffect(() => {
    void loadTableDetails();
  }, [loadTableDetails]);

  // Handle Sort Change
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
    setPage(1);
  };

  // Run SQL Query
  const handleRunSql = async () => {
    if (!sqlQuery.trim()) return;
    setIsExecutingSql(true);
    setSqlError(null);
    try {
      const result = await executeQuery(sqlQuery);
      setQueryResult(result);
      toast.success(`Query executed in ${result.duration_ms}ms (${result.row_count} rows)`);
    } catch (e: any) {
      setSqlError(e?.message || "Query execution failed");
      toast.error(e?.message || "Query execution failed");
    } finally {
      setIsExecutingSql(false);
    }
  };

  // Trigger Bulk Promotion to DB
  const handlePromoteAll = async () => {
    setIsPromotingAll(true);
    toast.info("Auto-promoting all extracted records to voters table...");
    try {
      const res = await promoteAllToDb();
      toast.success(
        `Database updated! ${res.created} voters inserted, ${res.updated} updated, ${res.skipped} skipped.`
      );
      void loadOverview();
      void loadTableDetails();
    } catch (e: any) {
      toast.error(e?.message || "Failed to promote records to database");
    } finally {
      setIsPromotingAll(false);
    }
  };

  // Export current table rows as CSV
  const handleExportCsv = () => {
    if (!rowsData || rowsData.rows.length === 0) {
      toast.warning("No data rows to export");
      return;
    }
    downloadCsv(`${selectedTable}_export.csv`, rowsData.columns, rowsData.rows);
    toast.success(`Exported ${rowsData.rows.length} rows to CSV`);
  };

  const totalPages = useMemo(() => {
    if (!rowsData || rowsData.total === 0) return 1;
    return Math.ceil(rowsData.total / pageSize);
  }, [rowsData, pageSize]);

  return (
    <div className="flex-1 flex flex-col overflow-hidden p-6 gap-4 min-h-0 bg-transparent">
      {/* Top Database Stats Banner */}
      <div className="serena-glass p-4 rounded-2xl border border-slate-200 dark:border-white/5 flex items-center justify-between gap-4 flex-wrap shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-serena-indigo/10 border border-serena-indigo/30 flex items-center justify-center shrink-0">
            <Database className="w-5 h-5 text-serena-indigo" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-bold text-slate-900 dark:text-white">
                SQLite Database Explorer
              </h2>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-emerald-500/10 border border-emerald-500/25 text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
                <CheckCircle2 className="w-3 h-3" /> Active Connection
              </span>
            </div>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
              Direct introspection & querying for curated electoral roll tables
            </p>
          </div>
        </div>

        {/* Database Metric Badges */}
        <div className="flex items-center gap-2.5 flex-wrap">
          {stats && (
            <>
              <div className="px-3 py-1.5 rounded-xl bg-slate-100 dark:bg-obsidian-950 border border-slate-200 dark:border-white/10 text-xs flex items-center gap-1.5">
                <HardDrive className="w-3.5 h-3.5 text-serena-amber" />
                <span className="text-slate-500 dark:text-slate-400">Size:</span>
                <span className="font-mono font-bold text-slate-800 dark:text-slate-200">
                  {stats.file_size_display}
                </span>
              </div>

              <div className="px-3 py-1.5 rounded-xl bg-slate-100 dark:bg-obsidian-950 border border-slate-200 dark:border-white/10 text-xs flex items-center gap-1.5">
                <Table2 className="w-3.5 h-3.5 text-serena-indigo" />
                <span className="text-slate-500 dark:text-slate-400">Tables:</span>
                <span className="font-mono font-bold text-slate-800 dark:text-slate-200">
                  {stats.table_count}
                </span>
              </div>

              <div className="px-3 py-1.5 rounded-xl bg-slate-100 dark:bg-obsidian-950 border border-slate-200 dark:border-white/10 text-xs flex items-center gap-1.5">
                <Layers className="w-3.5 h-3.5 text-serena-violet" />
                <span className="text-slate-500 dark:text-slate-400">Indexes:</span>
                <span className="font-mono font-bold text-slate-800 dark:text-slate-200">
                  {stats.index_count}
                </span>
              </div>
            </>
          )}

          {/* Quick Auto-Promote All to DB Button */}
          <button
            onClick={() => void handlePromoteAll()}
            disabled={isPromotingAll}
            className="px-3.5 py-1.5 rounded-xl bg-gradient-to-r from-serena-indigo to-serena-violet hover:from-indigo-500 hover:to-violet-500 text-white text-xs font-bold flex items-center gap-1.5 shadow-md shadow-serena-indigo/20 transition-all active:scale-95 disabled:opacity-50"
            title="Auto-insert / promote all pending OCR records into the curated voters table"
          >
            {isPromotingAll ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Sparkles className="w-3.5 h-3.5 text-indigo-200" />
            )}
            <span>Auto-Promote All</span>
          </button>

          {/* Truncate Entire DB Button */}
          <button
            onClick={() => setConfirmTruncate("all")}
            className="px-3.5 py-1.5 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 text-rose-600 dark:text-rose-400 text-xs font-bold flex items-center gap-1.5 shadow-xs transition-all active:scale-95"
            title="Truncate all data tables in SQLite database"
          >
            <Trash2 className="w-3.5 h-3.5 text-rose-500" />
            <span>Truncate DB</span>
          </button>

          <button
            onClick={() => {
              void loadOverview();
              void loadTableDetails();
            }}
            className="p-2 rounded-xl bg-slate-100 dark:bg-obsidian-950 hover:bg-slate-200 dark:hover:bg-obsidian-850 border border-slate-200 dark:border-white/10 text-slate-600 dark:text-slate-300 transition-colors"
            title="Refresh database"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Main Split Layout: Left Tables Sidebar + Right Table Workspace */}
      <div className="flex-1 flex gap-4 min-h-0 overflow-hidden">
        {/* Left Sidebar: Tables List */}
        <aside className="w-64 serena-glass rounded-2xl border border-slate-200 dark:border-white/5 p-3 flex flex-col gap-2 shrink-0">
          <div className="text-[11px] font-bold uppercase tracking-wider text-slate-400 px-2 py-1">
            Database Tables ({tables.length})
          </div>

          <div className="flex-1 overflow-y-auto space-y-1 pr-1">
            {isLoadingTables ? (
              <div className="flex items-center justify-center p-6 text-slate-400">
                <Loader2 className="w-5 h-5 animate-spin" />
              </div>
            ) : (
              tables.map((t) => {
                const isSelected = selectedTable === t.name;
                return (
                  <button
                    key={t.name}
                    onClick={() => {
                      setSelectedTable(t.name);
                      setPage(1);
                      setSearchQuery("");
                      setSortCol(undefined);
                    }}
                    className={`w-full text-left px-3 py-2 rounded-xl text-xs font-semibold flex items-center justify-between gap-2 transition-all ${
                      isSelected
                        ? "bg-gradient-to-r from-serena-indigo to-serena-violet text-white shadow-md shadow-serena-indigo/20 font-bold"
                        : "text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-obsidian-850"
                    }`}
                  >
                    <div className="flex items-center gap-2 truncate">
                      <Table2 className={`w-3.5 h-3.5 shrink-0 ${isSelected ? "text-white" : "text-serena-indigo"}`} />
                      <span className="truncate">{t.name}</span>
                    </div>
                    <span
                      className={`text-[10px] font-mono px-1.5 py-0.5 rounded-md font-bold ${
                        isSelected
                          ? "bg-white/20 text-white"
                          : "bg-slate-200 dark:bg-obsidian-950 text-slate-500 dark:text-slate-400"
                      }`}
                    >
                      {t.row_count.toLocaleString()}
                    </span>
                  </button>
                );
              })
            )}
          </div>
        </aside>

        {/* Right Main Table Content Area */}
        <section className="flex-1 serena-glass rounded-2xl border border-slate-200 dark:border-white/5 flex flex-col min-w-0 overflow-hidden">
          {/* Table Header Controls */}
          <div className="p-3.5 border-b border-slate-200 dark:border-white/5 flex items-center justify-between gap-3 flex-wrap bg-slate-50/50 dark:bg-obsidian-950/40">
            {/* Left Tabs */}
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => setActiveTab("rows")}
                className={`px-3 py-1.5 rounded-xl text-xs font-bold flex items-center gap-1.5 transition-all ${
                  activeTab === "rows"
                    ? "bg-serena-indigo text-white shadow-sm"
                    : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
                }`}
              >
                <Table2 className="w-3.5 h-3.5" />
                <span>Rows ({rowsData?.total?.toLocaleString() ?? 0})</span>
              </button>

              <button
                onClick={() => setActiveTab("columns")}
                className={`px-3 py-1.5 rounded-xl text-xs font-bold flex items-center gap-1.5 transition-all ${
                  activeTab === "columns"
                    ? "bg-serena-indigo text-white shadow-sm"
                    : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
                }`}
              >
                <Columns3 className="w-3.5 h-3.5" />
                <span>Schema ({columns.length} cols)</span>
              </button>

              <button
                onClick={() => setActiveTab("sql")}
                className={`px-3 py-1.5 rounded-xl text-xs font-bold flex items-center gap-1.5 transition-all ${
                  activeTab === "sql"
                    ? "bg-serena-indigo text-white shadow-sm"
                    : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
                }`}
              >
                <Terminal className="w-3.5 h-3.5" />
                <span>SQL Console</span>
              </button>
            </div>

            {/* Right Tools: Search, Export, Truncate Table, Page Size */}
            {activeTab === "rows" && (
              <div className="flex items-center gap-2 ml-auto flex-wrap">
                {/* Search */}
                <div className="relative w-40 sm:w-52">
                  <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                  <input
                    type="text"
                    placeholder={`Search ${selectedTable}…`}
                    value={searchQuery}
                    onChange={(e) => {
                      setSearchQuery(e.target.value);
                      setPage(1);
                    }}
                    className="w-full pl-8 pr-3 py-1.5 bg-white dark:bg-obsidian-950 border border-slate-200 dark:border-white/10 rounded-xl text-xs text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-1 focus:ring-serena-indigo"
                  />
                </div>

                {/* CSV Export Button */}
                <button
                  onClick={handleExportCsv}
                  className="px-3 py-1.5 rounded-xl bg-white dark:bg-obsidian-950 hover:bg-slate-100 dark:hover:bg-obsidian-850 border border-slate-200 dark:border-white/10 text-xs font-semibold text-slate-700 dark:text-slate-300 flex items-center gap-1.5 shadow-xs transition-colors"
                  title="Export current rows to CSV"
                >
                  <FileDown className="w-3.5 h-3.5 text-serena-emerald" />
                  <span className="hidden sm:inline">Export CSV</span>
                </button>

                {/* Truncate Single Table Button */}
                <button
                  onClick={() => setConfirmTruncate(selectedTable)}
                  className="px-3 py-1.5 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 text-xs font-semibold text-rose-600 dark:text-rose-400 flex items-center gap-1.5 shadow-xs transition-colors"
                  title={`Truncate / empty all rows from table ${selectedTable}`}
                >
                  <Trash2 className="w-3.5 h-3.5 text-rose-500" />
                  <span className="hidden sm:inline">Truncate Table</span>
                </button>
              </div>
            )}
          </div>

          {/* TAB 1: ROWS DATA GRID */}
          {activeTab === "rows" && (
            <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
              <div className="flex-1 overflow-auto">
                {isLoadingRows ? (
                  <div className="flex flex-col items-center justify-center h-full gap-2 text-slate-400">
                    <Loader2 className="w-8 h-8 animate-spin text-serena-indigo" />
                    <span className="text-xs">Loading table rows…</span>
                  </div>
                ) : !rowsData || rowsData.rows.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-full gap-2 text-slate-400 p-8 text-center">
                    <Database className="w-10 h-10 text-slate-300 dark:text-slate-600" />
                    <span className="text-sm font-semibold text-slate-700 dark:text-slate-300">
                      No rows found in {selectedTable}
                    </span>
                    <p className="text-xs text-slate-500">
                      {searchQuery
                        ? "Try clearing your search query"
                        : "Table is currently empty"}
                    </p>
                  </div>
                ) : (
                  <table className="w-full text-left text-xs border-collapse font-mono">
                    <thead className="sticky top-0 bg-slate-100 dark:bg-obsidian-950 border-b border-slate-200 dark:border-white/10 z-10 text-[11px] text-slate-500 dark:text-slate-400 font-bold uppercase tracking-wider">
                      <tr>
                        {rowsData.columns.map((col) => {
                          const isSorted = sortCol === col;
                          return (
                            <th
                              key={col}
                              onClick={() => handleSort(col)}
                              className="p-3 cursor-pointer hover:bg-slate-200/60 dark:hover:bg-obsidian-850 select-none whitespace-nowrap transition-colors"
                            >
                              <div className="flex items-center gap-1.5">
                                <span>{col}</span>
                                {isSorted ? (
                                  sortOrder === "asc" ? (
                                    <ArrowUp className="w-3 h-3 text-serena-indigo" />
                                  ) : (
                                    <ArrowDown className="w-3 h-3 text-serena-indigo" />
                                  )
                                ) : (
                                  <ArrowUpDown className="w-3 h-3 text-slate-400 opacity-40 hover:opacity-100" />
                                )}
                              </div>
                            </th>
                          );
                        })}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200 dark:divide-white/5">
                      {rowsData.rows.map((row, rIdx) => (
                        <tr
                          key={rIdx}
                          className="hover:bg-slate-100/70 dark:hover:bg-obsidian-850/60 transition-colors"
                        >
                          {rowsData.columns.map((col) => {
                            const val = row[col];
                            return (
                              <td
                                key={col}
                                className="p-3 text-slate-700 dark:text-slate-300 max-w-[280px] truncate"
                              >
                                <CellFormatter
                                  val={val}
                                  colName={col}
                                  onInspect={(content) =>
                                    setModalValue({ title: `${selectedTable} -> ${col}`, content })
                                  }
                                />
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>

              {/* Pagination Bar */}
              {rowsData && rowsData.total > 0 && (
                <div className="p-3 border-t border-slate-200 dark:border-white/5 bg-slate-50 dark:bg-obsidian-950 flex items-center justify-between gap-3 text-xs shrink-0">
                  <div className="text-slate-500 font-medium">
                    Showing {(page - 1) * pageSize + 1}–
                    {Math.min(page * pageSize, rowsData.total)} of {rowsData.total.toLocaleString()} rows
                  </div>

                  <div className="flex items-center gap-2">
                    <select
                      value={pageSize}
                      onChange={(e) => {
                        setPageSize(Number(e.target.value));
                        setPage(1);
                      }}
                      className="px-2 py-1 bg-white dark:bg-obsidian-900 border border-slate-200 dark:border-white/10 rounded-lg text-slate-700 dark:text-slate-300 outline-none"
                    >
                      <option value={25}>25 rows</option>
                      <option value={50}>50 rows</option>
                      <option value={100}>100 rows</option>
                    </select>

                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => setPage((p) => Math.max(1, p - 1))}
                        disabled={page === 1}
                        className="p-1.5 rounded-lg bg-white dark:bg-obsidian-900 hover:bg-slate-100 dark:hover:bg-obsidian-850 border border-slate-200 dark:border-white/10 disabled:opacity-40"
                      >
                        <ChevronLeft className="w-3.5 h-3.5" />
                      </button>
                      <span className="px-2 font-mono font-bold text-slate-700 dark:text-slate-300">
                        {page} / {totalPages}
                      </span>
                      <button
                        onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                        disabled={page >= totalPages}
                        className="p-1.5 rounded-lg bg-white dark:bg-obsidian-900 hover:bg-slate-100 dark:hover:bg-obsidian-850 border border-slate-200 dark:border-white/10 disabled:opacity-40"
                      >
                        <ChevronRight className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* TAB 2: SCHEMA COLUMNS */}
          {activeTab === "columns" && (
            <div className="flex-1 overflow-auto p-4 space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {columns.map((col) => (
                  <div
                    key={col.name}
                    className="p-3.5 rounded-xl bg-white dark:bg-obsidian-950 border border-slate-200 dark:border-white/5 flex items-start gap-3 shadow-xs"
                  >
                    <div className="w-8 h-8 rounded-lg bg-serena-indigo/10 flex items-center justify-center shrink-0">
                      {col.pk ? (
                        <Key className="w-4 h-4 text-serena-amber" />
                      ) : col.type.toUpperCase().includes("INT") ? (
                        <Hash className="w-4 h-4 text-serena-indigo" />
                      ) : (
                        <Type className="w-4 h-4 text-slate-500" />
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="font-bold text-xs text-slate-800 dark:text-slate-200 truncate">
                          {col.name}
                        </span>
                        {col.pk && (
                          <span className="px-1.5 py-0.2 rounded text-[9px] font-bold bg-amber-500/10 text-amber-500 border border-amber-500/30">
                            PRIMARY KEY
                          </span>
                        )}
                      </div>
                      <div className="text-[11px] font-mono text-serena-violet mt-1">
                        {col.type || "VARCHAR"}
                      </div>
                      <div className="text-[10px] text-slate-400 mt-1 flex items-center gap-2">
                        <span>{col.nullable ? "NULLABLE" : "NOT NULL"}</span>
                        {col.dflt_value && <span>Default: {col.dflt_value}</span>}
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              {indexes.length > 0 && (
                <div className="mt-6 pt-4 border-t border-slate-200 dark:border-white/5">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3">
                    Indexes ({indexes.length})
                  </h4>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {indexes.map((idx) => (
                      <div
                        key={idx.name}
                        className="p-3 rounded-xl bg-white dark:bg-obsidian-950 border border-slate-200 dark:border-white/5 text-xs font-mono"
                      >
                        <div className="font-bold text-slate-800 dark:text-slate-200 flex items-center gap-2">
                          <Layers className="w-3.5 h-3.5 text-serena-violet" />
                          <span>{idx.name}</span>
                          {idx.unique && (
                            <span className="px-1.5 py-0.2 text-[9px] rounded bg-emerald-500/10 text-emerald-500 border border-emerald-500/30">
                              UNIQUE
                            </span>
                          )}
                        </div>
                        <div className="text-[11px] text-slate-500 mt-1">
                          Columns: {idx.columns.join(", ")}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* TAB 3: SQL QUERY CONSOLE */}
          {activeTab === "sql" && (
            <div className="flex-1 flex flex-col min-h-0 overflow-hidden p-4 gap-3">
              {/* Quick SQL Presets */}
              <div className="flex items-center gap-1.5 overflow-x-auto pb-1 text-xs">
                <span className="text-[11px] text-slate-400 font-semibold uppercase tracking-wider shrink-0">
                  Quick Query:
                </span>
                {[
                  "SELECT * FROM voters LIMIT 50;",
                  "SELECT count(*) AS total_voters, gender FROM voters GROUP BY gender;",
                  "SELECT count(*) AS total, part_number FROM voters GROUP BY part_number ORDER BY total DESC;",
                  "SELECT * FROM files ORDER BY created_at DESC LIMIT 20;",
                  "SELECT * FROM polling_stations LIMIT 20;",
                ].map((q, idx) => (
                  <button
                    key={idx}
                    onClick={() => setSqlQuery(q)}
                    className="px-2.5 py-1 rounded-lg bg-slate-100 dark:bg-obsidian-950 hover:bg-slate-200 dark:hover:bg-obsidian-850 border border-slate-200 dark:border-white/5 font-mono text-[11px] text-slate-600 dark:text-slate-300 whitespace-nowrap"
                  >
                    {q.slice(0, 32)}…
                  </button>
                ))}
              </div>

              {/* SQL Textarea */}
              <div className="relative">
                <textarea
                  value={sqlQuery}
                  onChange={(e) => setSqlQuery(e.target.value)}
                  onKeyDown={(e) => {
                    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
                      void handleRunSql();
                    }
                  }}
                  rows={4}
                  placeholder="Enter custom SQL SELECT or PRAGMA query…"
                  className="w-full p-3.5 bg-white dark:bg-obsidian-950 border border-slate-200 dark:border-white/10 rounded-xl font-mono text-xs text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-serena-indigo/40 shadow-inner"
                />
                <button
                  onClick={() => void handleRunSql()}
                  disabled={isExecutingSql || !sqlQuery.trim()}
                  className="absolute right-3 bottom-3.5 px-4 py-2 rounded-xl bg-gradient-to-r from-serena-indigo to-serena-violet hover:from-indigo-500 hover:to-violet-500 text-white text-xs font-bold flex items-center gap-1.5 shadow-lg shadow-serena-indigo/20 disabled:opacity-50 transition-all active:scale-95"
                >
                  {isExecutingSql ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Play className="w-3.5 h-3.5 fill-white" />
                  )}
                  <span>Execute (Ctrl+Enter)</span>
                </button>
              </div>

              {/* SQL Error Banner */}
              {sqlError && (
                <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-500 text-xs font-mono flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 shrink-0" />
                  <span>{sqlError}</span>
                </div>
              )}

              {/* SQL Result Table */}
              <div className="flex-1 overflow-auto border border-slate-200 dark:border-white/10 rounded-xl bg-white dark:bg-obsidian-950">
                {queryResult ? (
                  <table className="w-full text-left text-xs font-mono border-collapse">
                    <thead className="sticky top-0 bg-slate-100 dark:bg-obsidian-900 border-b border-slate-200 dark:border-white/10 text-[11px] text-slate-500 uppercase tracking-wider">
                      <tr>
                        {queryResult.columns.map((c) => (
                          <th key={c} className="p-3 whitespace-nowrap font-bold">
                            {c}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200 dark:divide-white/5">
                      {queryResult.rows.map((row, i) => (
                        <tr key={i} className="hover:bg-slate-50 dark:hover:bg-obsidian-850">
                          {queryResult.columns.map((c) => (
                            <td key={c} className="p-3 text-slate-700 dark:text-slate-300 max-w-[300px] truncate">
                              <CellFormatter
                                val={row[c]}
                                colName={c}
                                onInspect={(content) =>
                                  setModalValue({ title: `Query Result -> ${c}`, content })
                                }
                              />
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <div className="flex items-center justify-center h-full text-xs text-slate-400">
                    Run a query to view results
                  </div>
                )}
              </div>
            </div>
          )}
        </section>
      </div>

      {/* JSON / Text Inspector Modal */}
      {modalValue && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="w-full max-w-2xl serena-glass rounded-3xl p-5 border border-slate-200 dark:border-white/10 shadow-2xl flex flex-col max-h-[85vh]">
            <div className="flex items-center justify-between pb-3 border-b border-slate-200 dark:border-white/10">
              <h3 className="text-xs font-bold font-mono text-slate-800 dark:text-slate-200">
                {modalValue.title}
              </h3>
              <button
                onClick={() => setModalValue(null)}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="flex-1 overflow-auto p-4 font-mono text-xs bg-slate-50 dark:bg-obsidian-950 rounded-xl my-3 text-slate-800 dark:text-slate-200 whitespace-pre-wrap select-text border border-slate-200 dark:border-white/5">
              {modalValue.content}
            </div>
            <div className="flex justify-end">
              <button
                onClick={() => setModalValue(null)}
                className="px-4 py-2 rounded-xl bg-serena-indigo text-white text-xs font-bold"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
      {/* Truncate Confirmation Modal */}
      {confirmTruncate && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-md flex items-center justify-center p-4">
          <div className="w-full max-w-md serena-glass rounded-3xl p-6 border border-rose-500/30 bg-white dark:bg-obsidian-900 shadow-2xl relative">
            <div className="flex items-center gap-3.5 mb-4">
              <div className="w-11 h-11 rounded-2xl bg-rose-500/15 border border-rose-500/30 flex items-center justify-center shrink-0">
                <AlertTriangle className="w-6 h-6 text-rose-500" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                  {confirmTruncate === "all"
                    ? "Truncate Entire Database?"
                    : `Truncate Table "${confirmTruncate}"?`}
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                  This action is irreversible and will permanently delete data.
                </p>
              </div>
            </div>

            <div className="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/20 text-xs text-rose-700 dark:text-rose-300 space-y-1.5 mb-5 font-medium">
              {confirmTruncate === "all" ? (
                <>
                  <p>• All voter records, OCR blocks, files, and job queues will be cleared.</p>
                  <p>• Database schema and table structures will remain intact.</p>
                </>
              ) : (
                <p>• All records in table <strong>{confirmTruncate}</strong> will be permanently wiped.</p>
              )}
            </div>

            <div className="flex items-center justify-end gap-2.5">
              <button
                onClick={() => setConfirmTruncate(null)}
                disabled={isTruncating}
                className="px-4 py-2 rounded-xl bg-slate-100 dark:bg-obsidian-950 hover:bg-slate-200 dark:hover:bg-obsidian-850 border border-slate-200 dark:border-white/10 text-xs font-semibold text-slate-700 dark:text-slate-300 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => void handleExecuteTruncate()}
                disabled={isTruncating}
                className="px-4 py-2 rounded-xl bg-gradient-to-r from-rose-600 to-red-600 hover:from-rose-500 hover:to-red-500 text-white text-xs font-bold flex items-center gap-1.5 shadow-lg shadow-rose-600/30 transition-all active:scale-95 disabled:opacity-50"
              >
                {isTruncating ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Trash2 className="w-4 h-4" />
                )}
                <span>Yes, Truncate Now</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

function CellFormatter({
  val,
  colName,
  onInspect,
}: {
  val: unknown;
  colName: string;
  onInspect: (str: string) => void;
}) {
  if (val === null || val === undefined) {
    return <span className="text-slate-400 dark:text-slate-600 italic">NULL</span>;
  }
  if (typeof val === "boolean") {
    return (
      <span className={`font-bold ${val ? "text-emerald-500" : "text-rose-500"}`}>
        {val ? "TRUE" : "FALSE"}
      </span>
    );
  }
  if (typeof val === "number") {
    return <span className="text-serena-indigo font-bold">{val.toLocaleString()}</span>;
  }

  const str = typeof val === "object" ? JSON.stringify(val, null, 2) : String(val);

  if (str.startsWith("{") || str.startsWith("[")) {
    return (
      <button
        onClick={() => onInspect(str)}
        className="px-2 py-0.5 rounded-md bg-amber-500/10 hover:bg-amber-500/20 text-amber-600 dark:text-amber-400 border border-amber-500/20 text-[10px] font-bold flex items-center gap-1"
      >
        <Eye className="w-3 h-3" />
        <span>JSON Data</span>
      </button>
    );
  }

  if (str.length > 50) {
    return (
      <span
        onClick={() => onInspect(str)}
        className="cursor-pointer hover:underline text-slate-700 dark:text-slate-300"
        title="Click to view full content"
      >
        {str.slice(0, 50)}…
      </span>
    );
  }

  return <span>{str}</span>;
}

"use client";

import React, { useEffect, useState, useCallback, useRef } from "react";
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
  Hash,
  Type,
  Play,
  Clock,
  HardDrive,
  Layers,
  Eye,
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  FileCode2,
} from "lucide-react";
import {
  fetchTables,
  fetchColumns,
  fetchRows,
  fetchIndexes,
  fetchDbStats,
  executeQuery,
  type DbTableInfo,
  type DbColumn,
  type DbIndex,
  type DbRowsResponse,
  type DbQueryResult,
  type DbStats,
} from "@/lib/databaseApi";

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StatCard({ icon: Icon, label, value }: { icon: React.ElementType; label: string; value: string }) {
  return (
    <div className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-white/5 border border-white/5">
      <Icon className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
      <span className="text-[10px] text-white/40 uppercase tracking-wider">{label}</span>
      <span className="text-xs font-bold text-white/80 ml-auto">{value}</span>
    </div>
  );
}

function CellValue({ value }: { value: unknown }) {
  if (value === null || value === undefined) {
    return <span className="text-white/20 italic text-[12px]">NULL</span>;
  }
  if (typeof value === "boolean") {
    return (
      <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[11px] font-mono font-medium ${value ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" : "bg-rose-500/10 text-rose-400 border border-rose-500/20"}`}>
        {value ? "true" : "false"}
      </span>
    );
  }
  if (typeof value === "number") {
    return <span className="text-[12px] font-mono text-sky-300 font-medium">{value.toLocaleString()}</span>;
  }
  const str = String(value);
  // JSON objects
  if (str.startsWith("{") || str.startsWith("[")) {
    return (
      <span className="text-[12px] font-mono text-amber-300/90 truncate block max-w-[400px]" title={str}>
        {str.length > 100 ? str.slice(0, 100) + "…" : str}
      </span>
    );
  }
  return (
    <span className="text-[12px] text-white/80 truncate block max-w-[400px]" title={str}>
      {str.length > 100 ? str.slice(0, 100) + "…" : str}
    </span>
  );
}

function ColumnBadge({ col }: { col: DbColumn }) {
  return (
    <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-white/[0.03] border border-white/5 hover:bg-white/[0.06] transition-colors">
      <div className="flex items-center gap-1.5 min-w-0 flex-1">
        {col.pk ? (
          <Key className="w-3.5 h-3.5 text-amber-400 shrink-0" />
        ) : (
          <Type className="w-3.5 h-3.5 text-white/20 shrink-0" />
        )}
        <span className="text-xs font-semibold text-white/90 truncate">{col.name}</span>
      </div>
      <div className="flex items-center gap-1.5 shrink-0">
        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-indigo-500/10 text-indigo-300 border border-indigo-500/20">
          {col.type}
        </span>
        {col.nullable && (
          <span className="text-[9px] px-1 py-0.5 rounded bg-white/5 text-white/30">NULLABLE</span>
        )}
        {col.pk && (
          <span className="text-[9px] px-1 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/20">
            PK
          </span>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function DatabaseView() {
  // --- State ---
  const [tables, setTables] = useState<DbTableInfo[]>([]);
  const [stats, setStats] = useState<DbStats | null>(null);
  const [activeTable, setActiveTable] = useState<string | null>(null);
  const [columns, setColumns] = useState<DbColumn[]>([]);
  const [indexes, setIndexes] = useState<DbIndex[]>([]);
  const [rowsData, setRowsData] = useState<DbRowsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [tableLoading, setTableLoading] = useState(false);
  const [tableSearch, setTableSearch] = useState("");
  const [entityFilter, setEntityFilter] = useState<"all" | "table" | "view">("all");
  const [rowSearch, setRowSearch] = useState("");
  const [sortCol, setSortCol] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [page, setPage] = useState(1);
  const [showSchema, setShowSchema] = useState(false);
  const [showSql, setShowSql] = useState(false);
  const [sqlInput, setSqlInput] = useState("SELECT * FROM view_voters_list LIMIT 10;");
  const [sqlResult, setSqlResult] = useState<DbQueryResult | null>(null);
  const [sqlError, setSqlError] = useState<string | null>(null);
  const [sqlRunning, setSqlRunning] = useState(false);
  const sqlRef = useRef<HTMLTextAreaElement>(null);

  const PAGE_SIZE = 50;

  // --- Initial load ---
  useEffect(() => {
    (async () => {
      try {
        const [t, s] = await Promise.all([fetchTables(), fetchDbStats()]);
        setTables(t);
        setStats(s);
        if (t.length > 0) setActiveTable(t[0].name);
      } catch {
        /* ignore */
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  // --- Load table data when activeTable changes ---
  const loadTableData = useCallback(
    async (table: string, pg = 1, sort?: string, dir?: "asc" | "desc", search?: string) => {
      setTableLoading(true);
      try {
        const [cols, idxs, rows] = await Promise.all([
          fetchColumns(table),
          fetchIndexes(table),
          fetchRows(table, {
            page: pg,
            page_size: PAGE_SIZE,
            sort: sort || undefined,
            order: dir || "asc",
            search: search || undefined,
          }),
        ]);
        setColumns(cols);
        setIndexes(idxs);
        setRowsData(rows);
      } catch {
        /* ignore */
      } finally {
        setTableLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    if (activeTable) {
      setPage(1);
      setSortCol(null);
      setSortDir("asc");
      setRowSearch("");
      setShowSchema(false);
      loadTableData(activeTable);
    }
  }, [activeTable, loadTableData]);

  // --- Handlers ---
  const handleSort = (col: string) => {
    const newDir = sortCol === col && sortDir === "asc" ? "desc" : "asc";
    setSortCol(col);
    setSortDir(newDir);
    setPage(1);
    if (activeTable) loadTableData(activeTable, 1, col, newDir, rowSearch);
  };

  const handlePageChange = (newPage: number) => {
    setPage(newPage);
    if (activeTable) loadTableData(activeTable, newPage, sortCol || undefined, sortDir, rowSearch);
  };

  const handleRowSearch = () => {
    setPage(1);
    if (activeTable) loadTableData(activeTable, 1, sortCol || undefined, sortDir, rowSearch);
  };

  const handleRefresh = () => {
    if (activeTable) loadTableData(activeTable, page, sortCol || undefined, sortDir, rowSearch);
    fetchTables().then(setTables).catch(() => null);
    fetchDbStats().then(setStats).catch(() => null);
  };

  const handleRunSql = async () => {
    setSqlRunning(true);
    setSqlError(null);
    setSqlResult(null);
    try {
      const result = await executeQuery(sqlInput);
      setSqlResult(result);
    } catch (err: unknown) {
      setSqlError(err instanceof Error ? err.message : String(err));
    } finally {
      setSqlRunning(false);
    }
  };

  // --- Computed ---
  const tableList = tables.filter((t) => (t.type || "table") === "table");
  const viewList = tables.filter((t) => t.type === "view");

  const filteredTables = tables.filter((t) => {
    const matchesSearch = t.name.toLowerCase().includes(tableSearch.toLowerCase());
    const matchesType = entityFilter === "all" || (t.type || "table") === entityFilter;
    return matchesSearch && matchesType;
  });

  const filteredOnlyTables = filteredTables.filter((t) => (t.type || "table") === "table");
  const filteredOnlyViews = filteredTables.filter((t) => t.type === "view");

  const totalPages = rowsData ? Math.ceil(rowsData.total / PAGE_SIZE) : 0;
  const activeInfo = tables.find((t) => t.name === activeTable);
  const isView = activeInfo?.type === "view";

  // --- Loading ---
  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="w-6 h-6 animate-spin text-emerald-400" />
          <p className="text-sm text-white/40">Loading database…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex overflow-hidden">
      {/* ── Left Panel: Supabase-Style Schema Explorer ── */}
      <div className="w-64 shrink-0 border-r border-white/5 flex flex-col bg-[hsl(var(--background))]">
        {/* Header & Filter Search */}
        <div className="p-3 border-b border-white/5 space-y-2.5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Database className="w-4 h-4 text-emerald-400" />
              <span className="text-xs font-bold text-white/90 uppercase tracking-wider">Schema Explorer</span>
            </div>
            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-white/5 text-white/40">
              {tables.length} objects
            </span>
          </div>

          {/* Type Filter Pills (All / Tables / Views) */}
          <div className="grid grid-cols-3 gap-1 bg-white/[0.03] p-0.5 rounded-lg border border-white/5">
            <button
              onClick={() => setEntityFilter("all")}
              className={`py-1 text-[10px] font-semibold rounded-md transition-all ${
                entityFilter === "all"
                  ? "bg-white/10 text-white shadow-sm"
                  : "text-white/40 hover:text-white/70"
              }`}
            >
              All ({tables.length})
            </button>
            <button
              onClick={() => setEntityFilter("table")}
              className={`py-1 text-[10px] font-semibold rounded-md transition-all ${
                entityFilter === "table"
                  ? "bg-emerald-500/20 text-emerald-300 shadow-sm border border-emerald-500/30"
                  : "text-white/40 hover:text-white/70"
              }`}
            >
              Tables ({tableList.length})
            </button>
            <button
              onClick={() => setEntityFilter("view")}
              className={`py-1 text-[10px] font-semibold rounded-md transition-all ${
                entityFilter === "view"
                  ? "bg-indigo-500/20 text-indigo-300 shadow-sm border border-indigo-500/30"
                  : "text-white/40 hover:text-white/70"
              }`}
            >
              Views ({viewList.length})
            </button>
          </div>

          {/* Search box */}
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3 h-3 text-white/20" />
            <input
              type="text"
              placeholder="Search tables & views…"
              value={tableSearch}
              onChange={(e) => setTableSearch(e.target.value)}
              className="w-full h-7 pl-8 pr-2 text-[11px] rounded-md bg-white/5 border border-white/5 text-white/80 placeholder:text-white/20 outline-none focus:border-emerald-500/40"
            />
          </div>
        </div>

        {/* Tree / Grouped List */}
        <div className="flex-1 overflow-y-auto py-2 px-2 space-y-3">
          {/* TABLES GROUP */}
          {filteredOnlyTables.length > 0 && (
            <div>
              <div className="px-2 py-1 flex items-center justify-between text-[10px] font-bold text-white/30 uppercase tracking-widest">
                <span className="flex items-center gap-1.5">
                  <Table2 className="w-3 h-3 text-emerald-400/60" />
                  Tables ({filteredOnlyTables.length})
                </span>
              </div>
              <div className="mt-0.5 space-y-0.5">
                {filteredOnlyTables.map((t) => (
                  <button
                    key={t.name}
                    onClick={() => setActiveTable(t.name)}
                    className={`w-full text-left px-2.5 py-1.5 rounded-lg flex items-center gap-2 transition-all text-xs group ${
                      activeTable === t.name
                        ? "bg-emerald-500/15 text-emerald-300 font-semibold border border-emerald-500/30 shadow-sm"
                        : "text-white/60 hover:bg-white/[0.04] hover:text-white/90"
                    }`}
                  >
                    <Table2 className={`w-3.5 h-3.5 shrink-0 ${activeTable === t.name ? "text-emerald-400" : "text-white/25 group-hover:text-white/50"}`} />
                    <span className="truncate flex-1 font-medium">{t.name}</span>
                    <span className={`text-[10px] font-mono shrink-0 px-1.5 py-0.5 rounded-full ${
                      activeTable === t.name
                        ? "bg-emerald-500/20 text-emerald-300"
                        : "bg-white/5 text-white/25"
                    }`}>
                      {t.row_count.toLocaleString()}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* VIEWS GROUP */}
          {filteredOnlyViews.length > 0 && (
            <div>
              <div className="px-2 py-1 flex items-center justify-between text-[10px] font-bold text-white/30 uppercase tracking-widest">
                <span className="flex items-center gap-1.5">
                  <Eye className="w-3 h-3 text-indigo-400/60" />
                  Views ({filteredOnlyViews.length})
                </span>
              </div>
              <div className="mt-0.5 space-y-0.5">
                {filteredOnlyViews.map((v) => (
                  <button
                    key={v.name}
                    onClick={() => setActiveTable(v.name)}
                    className={`w-full text-left px-2.5 py-1.5 rounded-lg flex items-center gap-2 transition-all text-xs group ${
                      activeTable === v.name
                        ? "bg-indigo-500/15 text-indigo-300 font-semibold border border-indigo-500/30 shadow-sm"
                        : "text-white/60 hover:bg-white/[0.04] hover:text-white/90"
                    }`}
                  >
                    <Eye className={`w-3.5 h-3.5 shrink-0 ${activeTable === v.name ? "text-indigo-400" : "text-white/25 group-hover:text-white/50"}`} />
                    <span className="truncate flex-1 font-medium">{v.name}</span>
                    <span className="text-[9px] font-bold uppercase tracking-wider px-1 py-0.5 rounded bg-indigo-500/10 text-indigo-300 border border-indigo-500/20">
                      VIEW
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {filteredTables.length === 0 && (
            <div className="text-center py-6">
              <p className="text-xs text-white/25">No matching tables or views</p>
            </div>
          )}
        </div>

        {/* DB Stats Footer */}
        {stats && (
          <div className="border-t border-white/5 p-3 space-y-1.5">
            <StatCard icon={HardDrive} label="Size" value={stats.file_size_display} />
            <StatCard icon={Layers} label="SQLite" value={stats.sqlite_version} />
            <StatCard icon={Hash} label="Indexes" value={String(stats.index_count)} />
          </div>
        )}
      </div>

      {/* ── Right Panel: Data Grid & Toolbar ── */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Toolbar */}
        <div className="h-12 shrink-0 border-b border-white/5 flex items-center gap-2 px-4 bg-[hsl(var(--background))]">
          {activeTable && (
            <div className="flex items-center gap-2 min-w-0">
              {isView ? (
                <Eye className="w-4 h-4 text-indigo-400 shrink-0" />
              ) : (
                <Table2 className="w-4 h-4 text-emerald-400 shrink-0" />
              )}
              <span className="text-sm font-bold text-white/90 truncate">{activeTable}</span>
              <span className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded border ${
                isView
                  ? "bg-indigo-500/10 text-indigo-300 border-indigo-500/20"
                  : "bg-emerald-500/10 text-emerald-300 border-emerald-500/20"
              }`}>
                {isView ? "VIEW" : "TABLE"}
              </span>
              {activeInfo && (
                <span className="text-[10px] text-white/30 hidden md:inline ml-1">
                  {activeInfo.row_count.toLocaleString()} rows · {activeInfo.column_count} columns
                </span>
              )}
            </div>
          )}

          <div className="flex-1" />

          {/* Row search */}
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3 h-3 text-white/20" />
            <input
              type="text"
              placeholder="Search rows…"
              value={rowSearch}
              onChange={(e) => setRowSearch(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleRowSearch()}
              className="h-7 w-48 pl-8 pr-2 text-[11px] rounded-md bg-white/5 border border-white/5 text-white/80 placeholder:text-white/20 outline-none focus:border-emerald-500/40"
            />
          </div>

          {/* Schema toggle */}
          <button
            onClick={() => setShowSchema(!showSchema)}
            className={`h-7 px-2.5 rounded-md text-[11px] font-medium flex items-center gap-1.5 transition-colors ${
              showSchema
                ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"
                : "bg-white/5 text-white/50 border border-white/5 hover:text-white/70"
            }`}
          >
            <Columns3 className="w-3.5 h-3.5" />
            Schema
          </button>

          {/* SQL toggle */}
          <button
            onClick={() => setShowSql(!showSql)}
            className={`h-7 px-2.5 rounded-md text-[11px] font-medium flex items-center gap-1.5 transition-colors ${
              showSql
                ? "bg-indigo-500/15 text-indigo-300 border border-indigo-500/30"
                : "bg-white/5 text-white/50 border border-white/5 hover:text-white/70"
            }`}
          >
            <Terminal className="w-3.5 h-3.5" />
            SQL Console
          </button>

          {/* Refresh */}
          <button
            onClick={handleRefresh}
            className="h-7 px-2 rounded-md bg-white/5 border border-white/5 text-white/50 hover:text-white/70 transition-colors"
            title="Refresh"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Schema Drawer */}
        {showSchema && activeTable && (
          <div className="border-b border-white/5 bg-white/[0.02] max-h-64 overflow-y-auto">
            <div className="p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-xs font-bold text-white/60 uppercase tracking-wider">
                  {isView ? "View Columns" : "Table Columns"} ({columns.length})
                </h3>
                {indexes.length > 0 && (
                  <span className="text-[10px] text-white/30">{indexes.length} indexes</span>
                )}
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-1.5">
                {columns.map((col) => (
                  <ColumnBadge key={col.name} col={col} />
                ))}
              </div>
              {indexes.length > 0 && (
                <div className="mt-3 pt-3 border-t border-white/5">
                  <h4 className="text-[10px] font-bold text-white/40 uppercase tracking-wider mb-2">Indexes</h4>
                  <div className="flex flex-wrap gap-1.5">
                    {indexes.map((idx) => (
                      <span
                        key={idx.name}
                        className="text-[10px] font-mono px-2 py-1 rounded bg-white/5 text-white/40"
                        title={`${idx.unique ? "UNIQUE " : ""}(${idx.columns.join(", ")})`}
                      >
                        {idx.unique && <Key className="w-2.5 h-2.5 inline mr-1 text-amber-400" />}
                        {idx.name}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* SQL Console */}
        {showSql && (
          <div className="border-b border-white/5 bg-white/[0.02]">
            <div className="p-4">
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-xs font-bold text-white/60 uppercase tracking-wider flex items-center gap-1.5">
                  <Terminal className="w-3.5 h-3.5 text-indigo-400" />
                  SQL Console
                  <span className="text-[9px] font-normal text-white/20 ml-1">(read-only: SELECT, PRAGMA, EXPLAIN)</span>
                </h3>
              </div>
              <div className="flex gap-2">
                <textarea
                  ref={sqlRef}
                  value={sqlInput}
                  onChange={(e) => setSqlInput(e.target.value)}
                  onKeyDown={(e) => {
                    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
                      e.preventDefault();
                      handleRunSql();
                    }
                  }}
                  rows={3}
                  className="flex-1 text-[11px] font-mono p-3 rounded-lg bg-slate-950 border border-white/10 text-emerald-300 placeholder:text-white/20 outline-none focus:border-indigo-500/40 resize-y min-h-[60px]"
                  placeholder="SELECT * FROM view_voters_list LIMIT 10;"
                  spellCheck={false}
                />
                <button
                  onClick={handleRunSql}
                  disabled={sqlRunning || !sqlInput.trim()}
                  className="h-10 px-4 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white text-[11px] font-bold flex items-center gap-1.5 transition-colors self-end"
                >
                  {sqlRunning ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Play className="w-3.5 h-3.5" />
                  )}
                  Run
                </button>
              </div>
              <p className="text-[10px] text-white/20 mt-1.5">Ctrl+Enter to execute</p>

              {/* SQL Error */}
              {sqlError && (
                <div className="mt-3 flex items-start gap-2 p-3 rounded-lg bg-rose-500/10 border border-rose-500/20">
                  <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                  <p className="text-xs text-rose-300">{sqlError}</p>
                </div>
              )}

              {/* SQL Result */}
              {sqlResult && (
                <div className="mt-3">
                  <div className="flex items-center gap-3 mb-2">
                    <div className="flex items-center gap-1.5">
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                      <span className="text-[11px] text-emerald-300 font-medium">
                        {sqlResult.row_count} row{sqlResult.row_count !== 1 ? "s" : ""}
                      </span>
                    </div>
                    <div className="flex items-center gap-1">
                      <Clock className="w-3 h-3 text-white/20" />
                      <span className="text-[10px] text-white/30">{sqlResult.duration_ms}ms</span>
                    </div>
                  </div>
                  {sqlResult.columns.length > 0 && (
                    <div className="rounded-xl border border-white/10 overflow-hidden max-h-64 overflow-auto custom-scrollbar shadow-xl bg-[#0f1115]">
                      <table className="w-full text-[12px] border-collapse text-left">
                        <thead>
                          <tr className="bg-[#16181d] border-b border-white/10">
                            {sqlResult.columns.map((c) => (
                              <th key={c} className="px-4 py-2.5 font-semibold text-white/50 whitespace-nowrap tracking-wider sticky top-0 bg-[#16181d] z-10 shadow-[0_1px_0_rgba(255,255,255,0.1)] uppercase text-[10px]">
                                {c}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-white/[0.04]">
                          {sqlResult.rows.map((row, i) => (
                            <tr key={i} className="hover:bg-white/[0.04] even:bg-white/[0.01] transition-colors group">
                              {sqlResult.columns.map((c) => (
                                <td key={c} className="px-4 py-2.5 whitespace-nowrap text-white/80 group-hover:text-white transition-colors">
                                  <CellValue value={row[c]} />
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Data Grid */}
        <div className="flex-1 overflow-auto">
          {tableLoading ? (
            <div className="flex items-center justify-center h-full">
              <Loader2 className="w-5 h-5 animate-spin text-emerald-400" />
            </div>
          ) : rowsData && rowsData.columns.length > 0 ? (
            <div className="w-full h-full relative custom-scrollbar bg-[#0f1115]">
              <table className="w-full text-[12px] border-collapse text-left">
                <thead>
                  <tr className="bg-[#16181d] border-b border-white/10">
                    <th className="px-4 py-3 font-semibold text-white/50 uppercase tracking-wider sticky top-0 left-0 z-30 bg-[#16181d] shadow-[inset_-1px_-1px_0_rgba(255,255,255,0.1)] w-12 text-center text-[10px]">
                      #
                    </th>
                    {rowsData.columns.map((col) => (
                      <th
                        key={col}
                        onClick={() => handleSort(col)}
                        className="px-4 py-3 font-semibold text-white/50 uppercase tracking-wider sticky top-0 z-20 bg-[#16181d] shadow-[0_1px_0_rgba(255,255,255,0.1)] cursor-pointer hover:text-white/80 transition-colors whitespace-nowrap select-none group text-[10px]"
                      >
                        <div className="flex items-center gap-1.5">
                          {col}
                          {sortCol === col ? (
                            sortDir === "asc" ? (
                              <ArrowUp className="w-3.5 h-3.5 text-emerald-400" />
                            ) : (
                              <ArrowDown className="w-3.5 h-3.5 text-emerald-400" />
                            )
                          ) : (
                            <ArrowUpDown className="w-3.5 h-3.5 text-white/0 group-hover:text-white/20 transition-colors" />
                          )}
                        </div>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/[0.04]">
                  {rowsData.rows.map((row, i) => (
                    <tr
                      key={i}
                      className="hover:bg-white/[0.04] even:bg-white/[0.01] transition-colors group"
                    >
                      <td className="px-4 py-2.5 text-[11px] font-mono text-white/30 sticky left-0 z-10 bg-inherit group-hover:bg-[#1a1c23] even:bg-[#13151a] odd:bg-[#0f1115] shadow-[inset_-1px_0_0_rgba(255,255,255,0.05)] text-center">
                        {(page - 1) * PAGE_SIZE + i + 1}
                      </td>
                      {rowsData.columns.map((col) => (
                        <td key={col} className="px-4 py-2.5 whitespace-nowrap text-white/80 group-hover:text-white transition-colors">
                          <CellValue value={row[col]} />
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                {isView ? (
                  <Eye className="w-10 h-10 mx-auto mb-2 text-white/10" />
                ) : (
                  <Table2 className="w-10 h-10 mx-auto mb-2 text-white/10" />
                )}
                <p className="text-xs text-white/30">
                  {isView ? "No data returned by this view" : "No data in this table"}
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Pagination */}
        {rowsData && totalPages > 0 && (
          <div className="h-10 shrink-0 border-t border-white/5 flex items-center justify-between px-4 bg-[hsl(var(--background))]">
            <span className="text-[10px] text-white/30">
              Showing {((page - 1) * PAGE_SIZE) + 1}–{Math.min(page * PAGE_SIZE, rowsData.total)} of{" "}
              {rowsData.total.toLocaleString()} {isView ? "records in view" : "rows"}
            </span>
            <div className="flex items-center gap-1">
              <button
                onClick={() => handlePageChange(page - 1)}
                disabled={page <= 1}
                className="h-7 w-7 rounded-md bg-white/5 border border-white/5 flex items-center justify-center text-white/40 hover:text-white/70 disabled:opacity-20 transition-colors"
              >
                <ChevronLeft className="w-3.5 h-3.5" />
              </button>
              {/* Show up to 5 page buttons */}
              {Array.from({ length: Math.min(5, totalPages) }, (_, idx) => {
                let pNum: number;
                if (totalPages <= 5) {
                  pNum = idx + 1;
                } else if (page <= 3) {
                  pNum = idx + 1;
                } else if (page >= totalPages - 2) {
                  pNum = totalPages - 4 + idx;
                } else {
                  pNum = page - 2 + idx;
                }
                return (
                  <button
                    key={pNum}
                    onClick={() => handlePageChange(pNum)}
                    className={`h-7 min-w-[28px] px-1.5 rounded-md text-[11px] font-medium transition-colors ${
                      page === pNum
                        ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"
                        : "bg-white/5 border border-white/5 text-white/40 hover:text-white/70"
                    }`}
                  >
                    {pNum}
                  </button>
                );
              })}
              <button
                onClick={() => handlePageChange(page + 1)}
                disabled={page >= totalPages}
                className="h-7 w-7 rounded-md bg-white/5 border border-white/5 flex items-center justify-center text-white/40 hover:text-white/70 disabled:opacity-20 transition-colors"
              >
                <ChevronRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowDownAZ,
  ArrowUpAZ,
  BadgeCheck,
  ChevronLeft,
  ChevronRight,
  Database,
  Download,
  FileSpreadsheet,
  FileText,
  Loader2,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  Users,
  X,
} from "lucide-react";
import { toast } from "sonner";
import { Voter, VoterQuery, VoterStats } from "@ocr/shared-types";
import {
  bulkDeleteVoters,
  deleteVoter,
  downloadVoterExport,
  listVoters,
  voterStats,
} from "@/lib/voterApi";
import { VoterFormModal } from "./VoterFormModal";

const PAGE_SIZES = [25, 50, 100, 200];

const COLUMNS: Array<{ key: string; label: string; sortable: boolean; className?: string }> = [
  { key: "serial", label: "S.No", sortable: true, className: "w-20" },
  { key: "epic", label: "EPIC ID", sortable: true, className: "w-36" },
  { key: "name", label: "பெயர் · Name", sortable: true },
  { key: "relation_name", label: "உறவினர் · Relation", sortable: false },
  { key: "house_number", label: "வீட்டு எண்", sortable: true, className: "w-28" },
  { key: "age", label: "வயது", sortable: true, className: "w-16" },
  { key: "gender", label: "பாலினம்", sortable: true, className: "w-24" },
  { key: "part_number", label: "Part", sortable: true, className: "w-20" },
];

function StatCard({
  icon: Icon,
  label,
  value,
  tone = "indigo",
}: {
  icon: React.ElementType;
  label: string;
  value: React.ReactNode;
  tone?: "indigo" | "emerald" | "amber" | "slate";
}) {
  const tones = {
    indigo: "bg-indigo-50 dark:bg-indigo-500/10 text-indigo-600 dark:text-indigo-300",
    emerald: "bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-300",
    amber: "bg-amber-50 dark:bg-amber-500/10 text-amber-600 dark:text-amber-300",
    slate: "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300",
  };
  return (
    <div className="flex items-center gap-3 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-4 py-3">
      <div className={`h-9 w-9 rounded-lg flex items-center justify-center shrink-0 ${tones[tone]}`}>
        <Icon className="h-4 w-4" />
      </div>
      <div className="min-w-0">
        <p className="text-[11px] font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400 truncate">
          {label}
        </p>
        <p className="text-lg font-bold text-slate-900 dark:text-slate-100 leading-tight">{value}</p>
      </div>
    </div>
  );
}

export const VotersView: React.FC = () => {
  const [rows, setRows] = useState<Voter[]>([]);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState<VoterStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [gender, setGender] = useState("");
  const [verified, setVerified] = useState<"" | "yes" | "no">("");
  const [sort, setSort] = useState("serial");
  const [order, setOrder] = useState<"asc" | "desc">("asc");
  const [pageSize, setPageSize] = useState(50);
  const [page, setPage] = useState(0);

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [editing, setEditing] = useState<Voter | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [exporting, setExporting] = useState<string | null>(null);

  // Debounce so typing does not fire a request per keystroke.
  useEffect(() => {
    const t = setTimeout(() => {
      setDebouncedSearch(search);
      setPage(0);
    }, 300);
    return () => clearTimeout(t);
  }, [search]);

  const query = useMemo<VoterQuery>(
    () => ({
      search: debouncedSearch || undefined,
      gender: gender || undefined,
      verified: verified === "" ? undefined : verified === "yes",
      sort,
      order,
      offset: page * pageSize,
      limit: pageSize,
    }),
    [debouncedSearch, gender, verified, sort, order, page, pageSize],
  );

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [data, s] = await Promise.all([listVoters(query), voterStats()]);
      setRows(data.items);
      setTotal(data.total);
      setStats(s);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load voters");
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    void load();
  }, [load]);

  const toggleSort = (key: string) => {
    if (sort === key) setOrder((o) => (o === "asc" ? "desc" : "asc"));
    else {
      setSort(key);
      setOrder("asc");
    }
    setPage(0);
  };

  const toggleRow = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const allOnPageSelected = rows.length > 0 && rows.every((r) => selected.has(r.id));

  const handleDelete = async (voter: Voter) => {
    if (!confirm(`Delete ${voter.name || voter.epic}? This cannot be undone.`)) return;
    try {
      await deleteVoter(voter.id);
      toast.success("Voter deleted");
      void load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Delete failed");
    }
  };

  const handleBulkDelete = async () => {
    if (!confirm(`Delete ${selected.size} selected voter(s)? This cannot be undone.`)) return;
    try {
      const res = await bulkDeleteVoters([...selected]);
      toast.success(`Deleted ${res.deleted} voter(s)`);
      setSelected(new Set());
      void load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Bulk delete failed");
    }
  };

  const handleExport = async (format: "xlsx" | "csv" | "pdf") => {
    setExporting(format);
    try {
      // Export what is on screen: same filters, no pagination.
      await downloadVoterExport(format, {
        search: debouncedSearch || undefined,
        gender: gender || undefined,
        verified: verified === "" ? undefined : verified === "yes",
        sort,
        order,
      });
      toast.success(`${format.toUpperCase()} downloaded`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Export failed");
    } finally {
      setExporting(null);
    }
  };

  const lastPage = Math.max(0, Math.ceil(total / pageSize) - 1);
  const filtersActive = Boolean(debouncedSearch || gender || verified);

  return (
    <div className="flex-1 flex flex-col min-w-0 overflow-hidden bg-slate-50 dark:bg-slate-950">
      {/* ---------------------------------------------------------- stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 p-4 pb-0">
        <StatCard icon={Users} label="Total voters" value={stats?.total ?? "—"} />
        <StatCard
          icon={BadgeCheck}
          label="Verified"
          value={stats?.verified ?? "—"}
          tone="emerald"
        />
        <StatCard
          icon={Database}
          label="Unverified"
          value={stats?.unverified ?? "—"}
          tone="amber"
        />
        <StatCard
          icon={Users}
          label="Average age"
          value={stats?.average_age ?? "—"}
          tone="slate"
        />
      </div>

      {/* -------------------------------------------------------- toolbar */}
      <div className="p-4 space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search name, EPIC, house number…"
              className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 pl-9 pr-8 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-500 transition"
            />
            {search && (
              <button
                onClick={() => setSearch("")}
                aria-label="Clear search"
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>

          <select
            value={gender}
            onChange={(e) => {
              setGender(e.target.value);
              setPage(0);
            }}
            className="rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-xs font-medium outline-none focus:ring-2 focus:ring-indigo-500/40"
          >
            <option value="">All genders</option>
            <option value="Male">Male</option>
            <option value="Female">Female</option>
            <option value="Other">Other</option>
          </select>

          <select
            value={verified}
            onChange={(e) => {
              setVerified(e.target.value as "" | "yes" | "no");
              setPage(0);
            }}
            className="rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-xs font-medium outline-none focus:ring-2 focus:ring-indigo-500/40"
          >
            <option value="">Any status</option>
            <option value="yes">Verified</option>
            <option value="no">Unverified</option>
          </select>

          <button
            onClick={() => void load()}
            title="Refresh"
            className="p-2 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 transition"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          </button>

          <button
            onClick={() => {
              setEditing(null);
              setFormOpen(true);
            }}
            className="px-3 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold flex items-center gap-1.5 shadow-sm transition"
          >
            <Plus className="h-4 w-4" />
            Add voter
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Export{filtersActive ? " (filtered)" : ""}:
          </span>
          {([
            { fmt: "xlsx" as const, icon: FileSpreadsheet, label: "Excel" },
            { fmt: "csv" as const, icon: FileText, label: "CSV" },
            { fmt: "pdf" as const, icon: FileText, label: "PDF" },
          ]).map(({ fmt, icon: Icon, label }) => (
            <button
              key={fmt}
              onClick={() => void handleExport(fmt)}
              disabled={exporting !== null}
              className="px-2.5 py-1.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-[11px] font-semibold text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-50 flex items-center gap-1.5 transition"
            >
              {exporting === fmt ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Icon className="h-3.5 w-3.5" />
              )}
              {label}
            </button>
          ))}

          {selected.size > 0 && (
            <div className="ml-auto flex items-center gap-2">
              <span className="text-[11px] font-semibold text-indigo-600 dark:text-indigo-300">
                {selected.size} selected
              </span>
              <button
                onClick={() => void handleBulkDelete()}
                className="px-2.5 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-500 text-white text-[11px] font-bold flex items-center gap-1.5 transition"
              >
                <Trash2 className="h-3.5 w-3.5" />
                Delete
              </button>
              <button
                onClick={() => setSelected(new Set())}
                className="px-2 py-1.5 rounded-lg text-[11px] font-semibold text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 transition"
              >
                Clear
              </button>
            </div>
          )}
        </div>
      </div>

      {/* ---------------------------------------------------------- table */}
      <div className="flex-1 overflow-auto px-4 pb-4">
        <div className="min-w-full overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
          <table className="w-full text-xs">
            <thead className="sticky top-0 z-10 bg-slate-50 dark:bg-slate-900/95 backdrop-blur border-b border-slate-200 dark:border-slate-800">
              <tr>
                <th className="w-10 px-3 py-2.5">
                  <input
                    type="checkbox"
                    checked={allOnPageSelected}
                    onChange={(e) =>
                      setSelected((prev) => {
                        const next = new Set(prev);
                        rows.forEach((r) => (e.target.checked ? next.add(r.id) : next.delete(r.id)));
                        return next;
                      })
                    }
                    aria-label="Select all rows on this page"
                    className="h-3.5 w-3.5 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500/40"
                  />
                </th>
                {COLUMNS.map((col) => (
                  <th
                    key={col.key}
                    className={`px-3 py-2.5 text-left font-bold uppercase tracking-wide text-[10px] text-slate-500 dark:text-slate-400 ${col.className ?? ""}`}
                  >
                    {col.sortable ? (
                      <button
                        onClick={() => toggleSort(col.key)}
                        className="inline-flex items-center gap-1 hover:text-slate-800 dark:hover:text-slate-200 transition"
                      >
                        {col.label}
                        {sort === col.key &&
                          (order === "asc" ? (
                            <ArrowUpAZ className="h-3 w-3" />
                          ) : (
                            <ArrowDownAZ className="h-3 w-3" />
                          ))}
                      </button>
                    ) : (
                      col.label
                    )}
                  </th>
                ))}
                <th className="w-24 px-3 py-2.5 text-right font-bold uppercase tracking-wide text-[10px] text-slate-500 dark:text-slate-400">
                  Actions
                </th>
              </tr>
            </thead>

            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {loading &&
                rows.length === 0 &&
                Array.from({ length: 8 }).map((_, i) => (
                  <tr key={`skeleton-${i}`}>
                    <td colSpan={COLUMNS.length + 2} className="px-3 py-2.5">
                      <div className="h-4 rounded bg-slate-100 dark:bg-slate-800 animate-pulse" />
                    </td>
                  </tr>
                ))}

              {!loading && rows.length === 0 && (
                <tr>
                  <td colSpan={COLUMNS.length + 2} className="px-3 py-16">
                    <div className="flex flex-col items-center gap-2 text-center">
                      <Database className="h-8 w-8 text-slate-300 dark:text-slate-700" />
                      <p className="text-sm font-semibold text-slate-700 dark:text-slate-300">
                        {filtersActive ? "No voters match these filters" : "No voters yet"}
                      </p>
                      <p className="text-xs text-slate-500 dark:text-slate-500 max-w-sm">
                        {filtersActive
                          ? "Try clearing the search or filters."
                          : "Promote reviewed records from the OCR workspace, or add a voter manually."}
                      </p>
                    </div>
                  </td>
                </tr>
              )}

              {rows.map((voter) => (
                <tr
                  key={voter.id}
                  className={`transition hover:bg-slate-50 dark:hover:bg-slate-800/50 ${
                    selected.has(voter.id) ? "bg-indigo-50/60 dark:bg-indigo-500/10" : ""
                  }`}
                >
                  <td className="px-3 py-2">
                    <input
                      type="checkbox"
                      checked={selected.has(voter.id)}
                      onChange={() => toggleRow(voter.id)}
                      aria-label={`Select ${voter.name}`}
                      className="h-3.5 w-3.5 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500/40"
                    />
                  </td>
                  <td className="px-3 py-2 text-slate-600 dark:text-slate-400">{voter.serial ?? "—"}</td>
                  <td className="px-3 py-2 font-mono text-slate-800 dark:text-slate-200">{voter.epic}</td>
                  <td className="px-3 py-2">
                    <span className="font-medium text-slate-900 dark:text-slate-100">{voter.name}</span>
                    {voter.verified && (
                      <BadgeCheck className="inline-block ml-1.5 h-3.5 w-3.5 text-emerald-500 align-text-bottom" />
                    )}
                  </td>
                  <td className="px-3 py-2 text-slate-600 dark:text-slate-400">
                    {voter.relation_name ? (
                      <>
                        <span className="text-[10px] uppercase text-slate-400 mr-1">
                          {voter.relation_type}
                        </span>
                        {voter.relation_name}
                      </>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="px-3 py-2 text-slate-600 dark:text-slate-400">{voter.house_number || "—"}</td>
                  <td className="px-3 py-2 text-slate-600 dark:text-slate-400">{voter.age ?? "—"}</td>
                  <td className="px-3 py-2">
                    {voter.gender ? (
                      <span
                        className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                          voter.gender === "Female"
                            ? "bg-fuchsia-50 dark:bg-fuchsia-500/10 text-fuchsia-700 dark:text-fuchsia-300"
                            : voter.gender === "Male"
                              ? "bg-sky-50 dark:bg-sky-500/10 text-sky-700 dark:text-sky-300"
                              : "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300"
                        }`}
                      >
                        {voter.gender}
                      </span>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="px-3 py-2 text-slate-600 dark:text-slate-400">{voter.part_number || "—"}</td>
                  <td className="px-3 py-2">
                    <div className="flex items-center justify-end gap-1">
                      <button
                        onClick={() => {
                          setEditing(voter);
                          setFormOpen(true);
                        }}
                        title="Edit"
                        className="p-1.5 rounded-lg text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 dark:hover:bg-indigo-500/10 transition"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </button>
                      <button
                        onClick={() => void handleDelete(voter)}
                        title="Delete"
                        className="p-1.5 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-500/10 transition"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {error && (
          <p className="mt-3 text-xs text-rose-600 dark:text-rose-400" role="alert">
            {error}
          </p>
        )}
      </div>

      {/* ----------------------------------------------------- pagination */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-4 py-2.5">
        <p className="text-[11px] text-slate-500 dark:text-slate-400">
          {total === 0
            ? "No records"
            : `Showing ${page * pageSize + 1}–${Math.min((page + 1) * pageSize, total)} of ${total}`}
        </p>

        <div className="flex items-center gap-3">
          <label className="flex items-center gap-1.5 text-[11px] text-slate-500 dark:text-slate-400">
            Rows
            <select
              value={pageSize}
              onChange={(e) => {
                setPageSize(Number(e.target.value));
                setPage(0);
              }}
              className="rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-1.5 py-1 text-[11px] outline-none"
            >
              {PAGE_SIZES.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>

          <div className="flex items-center gap-1">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              aria-label="Previous page"
              className="p-1.5 rounded-lg border border-slate-300 dark:border-slate-700 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-50 dark:hover:bg-slate-800 transition"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
            </button>
            <span className="text-[11px] text-slate-500 dark:text-slate-400 px-1">
              {page + 1} / {lastPage + 1}
            </span>
            <button
              onClick={() => setPage((p) => Math.min(lastPage, p + 1))}
              disabled={page >= lastPage}
              aria-label="Next page"
              className="p-1.5 rounded-lg border border-slate-300 dark:border-slate-700 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-50 dark:hover:bg-slate-800 transition"
            >
              <ChevronRight className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      </div>

      <VoterFormModal
        isOpen={formOpen}
        voter={editing}
        onClose={() => setFormOpen(false)}
        onSaved={() => void load()}
      />
    </div>
  );
};

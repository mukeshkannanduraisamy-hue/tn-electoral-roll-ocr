"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowDownAZ,
  ArrowUpAZ,
  BadgeCheck,
  ChevronLeft,
  ChevronRight,
  Download,
  Loader2,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  SlidersHorizontal,
  Trash2,
  Users,
  X,
  Filter,
  FileSpreadsheet,
  FileText,
  Database,
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
import { VoterProfilePage } from "./VoterProfilePage";

const PAGE_SIZES = [25, 50, 100, 200];

type SortKey = "serial" | "epic" | "name" | "age" | "gender" | "house_number" | "part_number" | "created_at";

function GenderBadge({ gender }: { gender: string }) {
  if (gender === "Male")
    return <span className="px-2 py-0.5 rounded-full text-[10px] font-bold badge-blue">{gender}</span>;
  if (gender === "Female")
    return <span className="px-2 py-0.5 rounded-full text-[10px] font-bold badge-rose">{gender}</span>;
  if (gender)
    return <span className="px-2 py-0.5 rounded-full text-[10px] font-bold badge-slate">{gender}</span>;
  return <span className="text-xs text-muted-foreground">—</span>;
}

function SortIcon({ col, sort, order }: { col: string; sort: string; order: string }) {
  if (sort !== col) return null;
  return order === "asc"
    ? <ArrowUpAZ className="w-3 h-3 text-primary inline-block ml-1" />
    : <ArrowDownAZ className="w-3 h-3 text-primary inline-block ml-1" />;
}

export const VotersView: React.FC = () => {
  const [rows, setRows] = useState<Voter[]>([]);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState<VoterStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [gender, setGender] = useState("");
  const [partNumber, setPartNumber] = useState("");
  const [minAge, setMinAge] = useState("");
  const [maxAge, setMaxAge] = useState("");
  const [verified, setVerified] = useState<"" | "true" | "false">("");
  const [sort, setSort] = useState<SortKey>("created_at");
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const [offset, setOffset] = useState(0);
  const [limit, setLimit] = useState(50);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [showFilters, setShowFilters] = useState(false);
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [editingVoter, setEditingVoter] = useState<Voter | null>(null);
  const [exportLoading, setExportLoading] = useState(false);
  const [openVoterId, setOpenVoterId] = useState<string | null>(null);

  // Listen for global profile open events
  useEffect(() => {
    const handler = (e: Event) => {
      const id = (e as CustomEvent).detail?.id;
      if (id) setOpenVoterId(id);
    };
    window.addEventListener("vims:open-voter", handler);
    return () => window.removeEventListener("vims:open-voter", handler);
  }, []);

  const loadData = useCallback(async () => {
    setLoading(true);
    setSelectedIds(new Set());
    try {
      const query: VoterQuery = {
        search: search || undefined,
        gender: gender || undefined,
        part_number: partNumber || undefined,
        verified: verified === "" ? undefined : verified === "true",
        min_age: minAge ? Number(minAge) : undefined,
        max_age: maxAge ? Number(maxAge) : undefined,
        sort,
        order,
        offset,
        limit,
      };
      const data = await listVoters(query);
      setRows(data.items || []);
      setTotal(data.total || 0);
    } catch {
      toast.error("Failed to load voters");
    } finally {
      setLoading(false);
    }
  }, [search, gender, partNumber, verified, minAge, maxAge, sort, order, offset, limit]);

  useEffect(() => { void loadData(); }, [loadData]);

  useEffect(() => {
    voterStats().then(setStats).catch(() => null);
  }, []);

  // Debounce search
  useEffect(() => {
    const t = setTimeout(() => {
      setSearch(searchInput);
      setOffset(0);
    }, 350);
    return () => clearTimeout(t);
  }, [searchInput]);

  const handleSort = (col: SortKey) => {
    if (sort === col) setOrder((o) => (o === "asc" ? "desc" : "asc"));
    else { setSort(col); setOrder("asc"); }
    setOffset(0);
  };

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === rows.length) setSelectedIds(new Set());
    else setSelectedIds(new Set(rows.map((r) => r.id)));
  };

  const handleDelete = async (id: string, name: string) => {
    if (!confirm(`Delete voter "${name}"?`)) return;
    try {
      await deleteVoter(id);
      toast.success("Voter deleted");
      void loadData();
    } catch { toast.error("Failed to delete"); }
  };

  const handleBulkDelete = async () => {
    if (!confirm(`Delete ${selectedIds.size} voter(s)?`)) return;
    try {
      const { deleted } = await bulkDeleteVoters([...selectedIds]);
      toast.success(`Deleted ${deleted} voter(s)`);
      void loadData();
    } catch { toast.error("Bulk delete failed"); }
  };

  const handleExport = async (format: "xlsx" | "csv") => {
    setExportLoading(true);
    try {
      await downloadVoterExport(format, {
        search: search || undefined,
        gender: gender || undefined,
        part_number: partNumber || undefined,
      });
    } catch (e: any) { toast.error(e?.message || "Export failed"); }
    finally { setExportLoading(false); }
  };

  const pages = Math.max(1, Math.ceil(total / limit));
  const currentPage = Math.floor(offset / limit) + 1;
  const hasFilters = !!(search || gender || partNumber || minAge || maxAge || verified);

  const clearFilters = () => {
    setSearchInput(""); setSearch(""); setGender("");
    setPartNumber(""); setMinAge(""); setMaxAge(""); setVerified("");
    setOffset(0);
  };

  const SortTh = ({ col, label, className = "" }: { col: SortKey; label: React.ReactNode; className?: string }) => (
    <th
      className={`cursor-pointer select-none hover:bg-muted/80 transition-colors ${className}`}
      onClick={() => handleSort(col)}
    >
      {label}
      <SortIcon col={col} sort={sort} order={order} />
    </th>
  );

  // Show voter profile if one is open
  if (openVoterId) {
    return (
      <VoterProfilePage
        voterId={openVoterId}
        onBack={() => setOpenVoterId(null)}
      />
    );
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden">

      {/* Header Bar */}
      <div className="shrink-0 px-6 py-4 border-b border-border bg-card/60 backdrop-blur-sm">
        <div className="flex items-center justify-between gap-4 mb-4">
          <div>
            <h1 className="text-lg font-bold text-foreground">Voters</h1>
            <p className="text-xs text-muted-foreground">
              {loading ? "Loading…" : `${total.toLocaleString()} voter${total !== 1 ? "s" : ""} in database`}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {selectedIds.size > 0 && (
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-rose-50 dark:bg-rose-500/10 border border-rose-200 dark:border-rose-500/20 text-rose-600 dark:text-rose-400 text-xs font-medium">
                <span>{selectedIds.size} selected</span>
                <button onClick={handleBulkDelete} className="flex items-center gap-1 hover:text-rose-700">
                  <Trash2 className="w-3.5 h-3.5" /> Delete
                </button>
              </div>
            )}
            {/* Export */}
            <div className="relative group">
              <button className="vims-btn-ghost h-8 text-xs" disabled={exportLoading}>
                {exportLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
                Export
              </button>
              <div className="absolute right-0 top-full mt-1 w-36 card-vims rounded-xl shadow-xl border border-border z-50 py-1 hidden group-hover:block">
                <button onClick={() => handleExport("xlsx")} className="flex items-center gap-2 px-3 py-2 text-xs w-full hover:bg-muted transition-colors">
                  <FileSpreadsheet className="w-3.5 h-3.5 text-green-500" />XLSX
                </button>
                <button onClick={() => handleExport("csv")} className="flex items-center gap-2 px-3 py-2 text-xs w-full hover:bg-muted transition-colors">
                  <FileText className="w-3.5 h-3.5 text-blue-500" />CSV
                </button>
              </div>
            </div>
            <button
              onClick={() => { setEditingVoter(null); setIsFormOpen(true); }}
              className="vims-btn-primary h-8 text-xs"
            >
              <Plus className="w-3.5 h-3.5" />
              Add Voter
            </button>
          </div>
        </div>

        {/* Search + Filter Row */}
        <div className="flex items-center gap-2">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground pointer-events-none" />
            <input
              type="text"
              placeholder="Search name, EPIC, house…"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              className="vims-input pl-9 h-8 text-xs"
            />
            {searchInput && (
              <button onClick={() => { setSearchInput(""); }} className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
          <button
            onClick={() => setShowFilters((v) => !v)}
            className={`vims-btn-ghost h-8 text-xs ${showFilters || hasFilters ? "bg-primary/10 text-primary border-primary/30" : ""}`}
          >
            <SlidersHorizontal className="w-3.5 h-3.5" />
            Filters
            {hasFilters && <span className="ml-1 w-4 h-4 rounded-full bg-primary text-white text-[9px] flex items-center justify-center">!</span>}
          </button>
          {hasFilters && (
            <button onClick={clearFilters} className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1">
              <X className="w-3 h-3" /> Clear
            </button>
          )}
          <button onClick={() => void loadData()} className="vims-btn-ghost h-8 w-8 p-0 justify-center" title="Refresh">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          </button>
          <select
            value={limit}
            onChange={(e) => { setLimit(Number(e.target.value)); setOffset(0); }}
            className="vims-input h-8 text-xs w-20 pr-2"
          >
            {PAGE_SIZES.map((s) => <option key={s} value={s}>{s} / pg</option>)}
          </select>
        </div>

        {/* Advanced Filters */}
        {showFilters && (
          <div className="flex flex-wrap items-center gap-2 mt-3 p-3 rounded-xl bg-muted/40 border border-border animate-fade-slide">
            <select value={gender} onChange={(e) => { setGender(e.target.value); setOffset(0); }} className="vims-input h-8 text-xs w-28">
              <option value="">All Genders</option>
              <option value="Male">Male</option>
              <option value="Female">Female</option>
              <option value="Other">Other</option>
            </select>
            <input type="text" placeholder="Part No." value={partNumber} onChange={(e) => { setPartNumber(e.target.value); setOffset(0); }} className="vims-input h-8 text-xs w-24" />
            <input type="number" placeholder="Min Age" value={minAge} onChange={(e) => { setMinAge(e.target.value); setOffset(0); }} className="vims-input h-8 text-xs w-20" />
            <input type="number" placeholder="Max Age" value={maxAge} onChange={(e) => { setMaxAge(e.target.value); setOffset(0); }} className="vims-input h-8 text-xs w-20" />
            <select value={verified} onChange={(e) => { setVerified(e.target.value as any); setOffset(0); }} className="vims-input h-8 text-xs w-32">
              <option value="">Any Status</option>
              <option value="true">Verified</option>
              <option value="false">Unverified</option>
            </select>
          </div>
        )}
      </div>

      {/* Stats chips */}
      {stats && (
        <div className="shrink-0 px-6 py-2.5 flex items-center gap-3 border-b border-border bg-muted/20 overflow-x-auto">
          {[
            { label: "Total", value: stats.total, color: "text-foreground" },
            { label: "Male", value: stats.by_gender?.["Male"] ?? 0, color: "text-blue-500" },
            { label: "Female", value: stats.by_gender?.["Female"] ?? 0, color: "text-rose-500" },
            { label: "Verified", value: stats.verified, color: "text-green-500" },
            { label: "Avg Age", value: stats.average_age ? `${stats.average_age}y` : "—", color: "text-amber-500" },
          ].map(({ label, value, color }) => (
            <div key={label} className="flex items-center gap-1.5 whitespace-nowrap">
              <span className="text-[10px] text-muted-foreground font-medium">{label}</span>
              <span className={`text-xs font-bold ${color}`}>{typeof value === "number" ? value.toLocaleString() : value}</span>
            </div>
          ))}
        </div>
      )}

      {/* Table */}
      <div className="flex-1 overflow-auto">
        {loading && rows.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-3">
            <Loader2 className="w-6 h-6 animate-spin text-primary" />
            <p className="text-sm text-muted-foreground">Loading voters…</p>
          </div>
        ) : rows.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-3">
            <Users className="w-10 h-10 text-muted-foreground/30" />
            <p className="text-sm font-medium text-muted-foreground">No voters found</p>
            {hasFilters && (
              <button onClick={clearFilters} className="text-xs text-primary hover:underline">Clear filters</button>
            )}
          </div>
        ) : (
          <table className="vims-table">
            <thead>
              <tr>
                <th className="w-10 text-center">
                  <input
                    type="checkbox"
                    checked={selectedIds.size === rows.length && rows.length > 0}
                    onChange={toggleSelectAll}
                    className="rounded border-border"
                  />
                </th>
                <SortTh col="serial"       label="S.No" className="w-16" />
                <SortTh col="epic"         label="EPIC" className="w-36" />
                <SortTh col="name"         label="Name" />
                <th>Relative</th>
                <SortTh col="house_number" label="House" className="w-24" />
                <SortTh col="age"          label="Age" className="w-14" />
                <SortTh col="gender"       label="Gender" className="w-24" />
                <SortTh col="part_number"  label="Part" className="w-16" />
                <th className="w-20 text-center">Status</th>
                <th className="w-16 text-center">Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((voter) => {
                const initials = (voter.name || "?")[0].toUpperCase();
                const isSelected = selectedIds.has(voter.id);
                return (
                  <tr
                    key={voter.id}
                    onClick={() => setOpenVoterId(voter.id)}
                    className={`${isSelected ? "bg-primary/5" : ""}`}
                  >
                    <td className="text-center" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => toggleSelect(voter.id)}
                        className="rounded border-border"
                      />
                    </td>
                    <td className="text-xs text-muted-foreground font-mono">{voter.serial ?? "—"}</td>
                    <td>
                      <span className="font-mono text-xs text-primary bg-primary/8 px-2 py-0.5 rounded-md">
                        {voter.epic}
                      </span>
                    </td>
                    <td>
                      <div className="flex items-center gap-2.5">
                        <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-indigo-400 to-violet-500 flex items-center justify-center text-white font-bold text-[11px] shrink-0">
                          {initials}
                        </div>
                        <span className="font-medium text-sm truncate max-w-[160px]">
                          {voter.name || "—"}
                        </span>
                      </div>
                    </td>
                    <td className="text-xs text-muted-foreground">
                      <span className="text-[10px] text-muted-foreground mr-1">{voter.relation_type}</span>
                      <span className="truncate max-w-[100px] inline-block">{voter.relation_name || "—"}</span>
                    </td>
                    <td className="text-xs text-muted-foreground font-mono">{voter.house_number || "—"}</td>
                    <td className="text-xs font-semibold text-foreground text-center">{voter.age ?? "—"}</td>
                    <td><GenderBadge gender={voter.gender || ""} /></td>
                    <td className="text-xs text-muted-foreground text-center">{voter.part_number || "—"}</td>
                    <td className="text-center">
                      {voter.verified && (
                        <BadgeCheck className="w-4 h-4 text-green-500 mx-auto" />
                      )}
                    </td>
                    <td onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center justify-center gap-1">
                        <button
                          onClick={() => { setEditingVoter(voter); setIsFormOpen(true); }}
                          className="w-6 h-6 flex items-center justify-center rounded hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
                        >
                          <Pencil className="w-3 h-3" />
                        </button>
                        <button
                          onClick={() => handleDelete(voter.id, voter.name || voter.epic)}
                          className="w-6 h-6 flex items-center justify-center rounded hover:bg-rose-50 dark:hover:bg-rose-500/10 transition-colors text-muted-foreground hover:text-rose-500"
                        >
                          <Trash2 className="w-3 h-3" />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      <div className="shrink-0 flex items-center justify-between px-6 py-3 border-t border-border bg-card/60 backdrop-blur-sm">
        <div className="text-xs text-muted-foreground">
          Showing {offset + 1}–{Math.min(offset + limit, total)} of {total.toLocaleString()} voters
        </div>
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => setOffset((o) => Math.max(0, o - limit))}
            disabled={currentPage === 1}
            className="vims-btn-ghost h-7 w-7 p-0 justify-center disabled:opacity-40"
          >
            <ChevronLeft className="w-3.5 h-3.5" />
          </button>
          <span className="text-xs font-medium text-foreground px-2">
            {currentPage} / {pages}
          </span>
          <button
            onClick={() => setOffset((o) => Math.min((pages - 1) * limit, o + limit))}
            disabled={currentPage === pages}
            className="vims-btn-ghost h-7 w-7 p-0 justify-center disabled:opacity-40"
          >
            <ChevronRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {isFormOpen && (
        <VoterFormModal
          isOpen={isFormOpen}
          voter={editingVoter ?? undefined}
          onClose={() => { setIsFormOpen(false); setEditingVoter(null); }}
          onSaved={(_v) => { setIsFormOpen(false); setEditingVoter(null); void loadData(); }}
        />
      )}
    </div>
  );
};

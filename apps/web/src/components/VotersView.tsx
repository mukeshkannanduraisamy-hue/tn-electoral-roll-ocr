"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowDownAZ,
  ArrowUpAZ,
  BadgeCheck,
  Check,
  ChevronLeft,
  ChevronRight,
  Columns3,
  Copy,
  Download,
  Eye,
  FileSpreadsheet,
  FileText,
  Filter,
  Image as ImageIcon,
  Loader2,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  SlidersHorizontal,
  Trash2,
  UserCheck,
  Users,
  X,
  Code2,
  Building2,
  BookOpen,
  Calendar,
  FileCode,
  User,
  ShieldCheck,
  RotateCcw,
  Sparkles,
} from "lucide-react";
import { toast } from "sonner";
import { Voter, VoterQuery, VoterStats } from "@ocr/shared-types";
import { AiCustomizerModal } from "./AiCustomizerModal";
import {
  bulkDeleteVoters,
  deleteVoter,
  downloadVoterExport,
  listVoters,
  updateVoter,
  voterStats,
} from "@/lib/voterApi";
import { VoterFormModal } from "./VoterFormModal";
import { VoterProfilePage } from "./VoterProfilePage";

const PAGE_SIZES = [25, 50, 100, 200];

type SortKey = "serial" | "epic" | "name" | "age" | "gender" | "house_number" | "part_number" | "created_at";

export interface ColumnCategory {
  category: string;
  columns: { key: string; label: string }[];
}

const CATEGORIZED_COLUMNS: ColumnCategory[] = [
  {
    category: "Voter Identity",
    columns: [
      { key: "serial", label: "S.No" },
      { key: "epic", label: "EPIC ID" },
      { key: "name", label: "Voter Name" },
      { key: "relation_type", label: "Relation Type" },
      { key: "relation_name", label: "Relative Name" },
      { key: "house_number", label: "House No" },
      { key: "age", label: "Age" },
      { key: "gender", label: "Gender" },
    ],
  },
  {
    category: "Polling & Location",
    columns: [
      { key: "part_number", label: "Part No." },
      { key: "constituency", label: "Constituency" },
      { key: "polling_station_id", label: "Polling Station ID" },
      { key: "is_supplement", label: "Roll Type (Supplement)" },
    ],
  },
  {
    category: "PDF Source & Provenance",
    columns: [
      { key: "source_file_name", label: "Source PDF Name" },
      { key: "page_number", label: "Page No." },
      { key: "source_file_id", label: "Source File ID" },
      { key: "source_page_id", label: "Source Page ID" },
      { key: "source_record_id", label: "Source Record ID" },
    ],
  },
  {
    category: "Audit & Metadata",
    columns: [
      { key: "verified", label: "Verification Status" },
      { key: "notes", label: "Reviewer Notes" },
      { key: "created_at", label: "Date Added" },
      { key: "updated_at", label: "Date Modified" },
      { key: "created_by", label: "Created By" },
      { key: "updated_by", label: "Updated By" },
      { key: "actions", label: "Actions" },
    ],
  },
];

const DEFAULT_VISIBLE_COLUMNS = [
  "serial", "epic", "name", "relation_type", "relation_name",
  "house_number", "age", "gender", "part_number", "is_supplement",
  "verified", "actions",
];

const ALL_COLUMN_KEYS = CATEGORIZED_COLUMNS.flatMap((cat) => cat.columns.map((c) => c.key));

function GenderBadge({ gender, onClick }: { gender: string; onClick?: (e: React.MouseEvent) => void }) {
  if (!gender) return <span className="text-xs text-muted-foreground">—</span>;
  
  const getStyle = (g: string) => {
    if (g === "Male") return "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20 hover:bg-blue-500/20";
    if (g === "Female") return "bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20 hover:bg-rose-500/20";
    return "bg-slate-500/10 text-slate-600 dark:text-slate-400 border-slate-500/20 hover:bg-slate-500/20";
  };

  return (
    <span
      onClick={onClick}
      title={`Click to filter by Gender: ${gender}`}
      className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold border transition-all cursor-pointer inline-flex items-center space-x-1 ${getStyle(gender)}`}
    >
      <span>{gender}</span>
    </span>
  );
}

function RelationBadge({ type, name, onTypeClick, onNameClick }: { type: string; name: string; onTypeClick?: (e: React.MouseEvent) => void; onNameClick?: (e: React.MouseEvent) => void }) {
  if (!type && !name) return <span className="text-xs text-muted-foreground">—</span>;
  
  const getBadgeStyle = (t: string) => {
    switch (t?.toLowerCase()) {
      case "husband":
        return "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20 hover:bg-emerald-500/20";
      case "father":
        return "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20 hover:bg-amber-500/20";
      case "mother":
        return "bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/20 hover:bg-purple-500/20";
      default:
        return "bg-slate-500/10 text-slate-600 dark:text-slate-400 border-slate-500/20 hover:bg-slate-500/20";
    }
  };

  return (
    <div className="flex items-center gap-1.5 max-w-[180px]">
      {type && (
        <span
          onClick={onTypeClick}
          title={`Click to filter by Relation: ${type}`}
          className={`px-1.5 py-0.5 rounded text-[9px] font-extrabold uppercase border cursor-pointer transition-all ${getBadgeStyle(type)} shrink-0`}
        >
          {type}
        </span>
      )}
      <span
        onClick={onNameClick}
        title={name ? `Click to search for "${name}"` : undefined}
        className="text-xs font-medium text-slate-700 dark:text-slate-300 truncate cursor-pointer hover:underline"
      >
        {name || "—"}
      </span>
    </div>
  );
}

function SortIcon({ col, sort, order }: { col: string; sort: string; order: string }) {
  if (sort !== col) return null;
  return order === "asc"
    ? <ArrowUpAZ className="w-3.5 h-3.5 text-indigo-600 dark:text-indigo-400 inline-block ml-1" />
    : <ArrowDownAZ className="w-3.5 h-3.5 text-indigo-600 dark:text-indigo-400 inline-block ml-1" />;
}

export const VotersView: React.FC = () => {
  const [rows, setRows] = useState<Voter[]>([]);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState<VoterStats | null>(null);
  const [loading, setLoading] = useState(true);
  
  // Filtering States
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [gender, setGender] = useState("");
  const [relationType, setRelationType] = useState("");
  const [partNumber, setPartNumber] = useState("");
  const [houseNumber, setHouseNumber] = useState("");
  const [hasPhoto, setHasPhoto] = useState<"" | "true" | "false">("");
  const [minAge, setMinAge] = useState("");
  const [maxAge, setMaxAge] = useState("");
  const [verified, setVerified] = useState<"" | "true" | "false">("");
  const [agePreset, setAgePreset] = useState<"" | "18-25" | "26-40" | "41-60" | "60+">("");

  // Polling Details & Comprehensive Filters
  const [pollingStationId, setPollingStationId] = useState("");
  const [isSupplement, setIsSupplement] = useState<"" | "true" | "false">("");
  const [minSerial, setMinSerial] = useState("");
  const [maxSerial, setMaxSerial] = useState("");
  const [minPage, setMinPage] = useState("");
  const [maxPage, setMaxPage] = useState("");
  const [constituency, setConstituency] = useState("");
  const [sourceFileName, setSourceFileName] = useState("");

  // All 23 Database Columns Visibility Chooser
  const [visibleCols, setVisibleCols] = useState<Set<string>>(() => {
    if (typeof window !== "undefined") {
      const saved = localStorage.getItem("voter_db_columns_v3");
      if (saved) {
        try { return new Set(JSON.parse(saved)); } catch {}
      }
    }
    return new Set(DEFAULT_VISIBLE_COLUMNS);
  });
  const [showColChooser, setShowColChooser] = useState(false);

  // Sorting & Pagination
  const [sort, setSort] = useState<SortKey>("created_at");
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const [offset, setOffset] = useState(0);
  const [limit, setLimit] = useState(50);
  
  // UI Interactions
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [showFilters, setShowFilters] = useState(false);
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [editingVoter, setEditingVoter] = useState<Voter | null>(null);
  const [exportLoading, setExportLoading] = useState(false);
  const [openVoterId, setOpenVoterId] = useState<string | null>(null);
  const [copiedEpic, setCopiedEpic] = useState<string | null>(null);
  const [showAiCustomizer, setShowAiCustomizer] = useState(false);

  const handleApplyTheme = (theme: string) => {
    if (typeof document !== "undefined") {
      document.body.classList.remove("theme-emerald", "theme-purple", "theme-amber", "theme-ocean", "dark");
      if (theme === "dark") {
        document.body.classList.add("dark");
      } else if (theme !== "light") {
        document.body.classList.add(`theme-${theme}`);
      }
    }
  };

  const handleAiFilter = (filters: any) => {
    if (filters.gender) setGender(filters.gender);
    if (filters.minAge) setMinAge(filters.minAge);
    if (filters.maxAge) setMaxAge(filters.maxAge);
    if (filters.verified !== undefined) setVerified(filters.verified);
    if (filters.houseNumber) setHouseNumber(filters.houseNumber);
    if (filters.relationType) setRelationType(filters.relationType);
    setOffset(0);
  };

  const handleAiColumns = (preset: "all" | "basic" | "identity") => {
    if (preset === "all") {
      selectAllColumns();
    } else {
      resetDefaultColumns();
    }
  };

  const handleAiExport = (format: "excel" | "csv" | "json") => {
    if (format === "excel") void handleExport("xlsx");
    else if (format === "csv") void handleExport("csv");
    else if (format === "json") handleJSONExport();
  };

  const handleAiReset = () => {
    clearFilters();
    resetDefaultColumns();
    handleApplyTheme("light");
  };

  // Save Column Visibility
  const toggleColumnVisibility = (colKey: string) => {
    setVisibleCols((prev) => {
      const next = new Set(prev);
      if (next.has(colKey)) {
        if (next.size > 2) next.delete(colKey);
      } else {
        next.add(colKey);
      }
      if (typeof window !== "undefined") {
        localStorage.setItem("voter_db_columns_v3", JSON.stringify([...next]));
      }
      return next;
    });
  };

  const selectAllColumns = () => {
    const all = new Set(ALL_COLUMN_KEYS);
    setVisibleCols(all);
    if (typeof window !== "undefined") {
      localStorage.setItem("voter_db_columns_v3", JSON.stringify([...all]));
    }
  };

  const resetDefaultColumns = () => {
    const def = new Set(DEFAULT_VISIBLE_COLUMNS);
    setVisibleCols(def);
    if (typeof window !== "undefined") {
      localStorage.setItem("voter_db_columns_v3", JSON.stringify([...def]));
    }
  };

  // Cell Click-to-Filter Helper
  const filterByCellValue = (field: string, val: any) => {
    if (val === undefined || val === null || val === "") return;
    setOffset(0);
    switch (field) {
      case "gender":
        setGender(String(val));
        toast.info(`Filtered by Gender: ${val}`);
        break;
      case "relation_type":
        setRelationType(String(val));
        toast.info(`Filtered by Relation: ${val}`);
        break;
      case "part_number":
        setPartNumber(String(val));
        toast.info(`Filtered by Part No.: ${val}`);
        break;
      case "constituency":
        setConstituency(String(val));
        toast.info(`Filtered by Constituency: ${val}`);
        break;
      case "polling_station_id":
        setPollingStationId(String(val));
        toast.info(`Filtered by Polling Station: ${val}`);
        break;
      case "is_supplement":
        setIsSupplement(val ? "true" : "false");
        toast.info(`Filtered by Roll Type: ${val ? "Supplement Roll" : "Main Roll"}`);
        break;
      case "house_number":
        setHouseNumber(String(val));
        toast.info(`Filtered by House No.: ${val}`);
        break;
      case "source_file_name":
        setSourceFileName(String(val));
        toast.info(`Filtered by Source File: ${val}`);
        break;
      case "age":
        setMinAge(String(val));
        setMaxAge(String(val));
        toast.info(`Filtered by Age: ${val}`);
        break;
      case "name":
      case "relation_name":
        setSearchInput(String(val));
        setSearch(String(val));
        toast.info(`Searching for "${val}"`);
        break;
    }
  };

  // Global event listener for voter profiles and AI customizer
  useEffect(() => {
    const handler = (e: Event) => {
      const id = (e as CustomEvent).detail?.id;
      if (id) setOpenVoterId(id);
    };
    const customizerHandler = () => {
      setShowAiCustomizer(true);
    };
    window.addEventListener("vi-mc:open-voter", handler);
    window.addEventListener("vi-mc:open-ai-customizer", customizerHandler);
    return () => {
      window.removeEventListener("vi-mc:open-voter", handler);
      window.removeEventListener("vi-mc:open-ai-customizer", customizerHandler);
    };
  }, []);

  // Fetch Voter List
  const loadData = useCallback(async () => {
    setLoading(true);
    setSelectedIds(new Set());
    try {
      const query: VoterQuery = {
        search: search || undefined,
        gender: gender || undefined,
        relation_type: relationType || undefined,
        part_number: partNumber || undefined,
        constituency: constituency || undefined,
        house_number: houseNumber || undefined,
        has_photo: hasPhoto === "" ? undefined : hasPhoto === "true",
        polling_station_id: pollingStationId || undefined,
        is_supplement: isSupplement === "" ? undefined : isSupplement === "true",
        min_serial: minSerial ? Number(minSerial) : undefined,
        max_serial: maxSerial ? Number(maxSerial) : undefined,
        min_page: minPage ? Number(minPage) : undefined,
        max_page: maxPage ? Number(maxPage) : undefined,
        source_file_name: sourceFileName || undefined,
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
    } catch (err: any) {
      toast.error(err?.message || "Failed to load voters dataset");
    } finally {
      setLoading(false);
    }
  }, [search, gender, relationType, partNumber, constituency, houseNumber, hasPhoto, pollingStationId, isSupplement, minSerial, maxSerial, minPage, maxPage, sourceFileName, verified, minAge, maxAge, sort, order, offset, limit]);

  useEffect(() => { void loadData(); }, [loadData]);

  // Fetch Dashboard Stats
  useEffect(() => {
    voterStats().then(setStats).catch(() => null);
  }, []);

  // Search Debouncing
  useEffect(() => {
    const t = setTimeout(() => {
      setSearch(searchInput);
      setOffset(0);
    }, 300);
    return () => clearTimeout(t);
  }, [searchInput]);

  // Handle Age Presets
  const handleAgePreset = (preset: "" | "18-25" | "26-40" | "41-60" | "60+") => {
    setAgePreset(preset);
    setOffset(0);
    if (!preset) {
      setMinAge("");
      setMaxAge("");
      return;
    }
    switch (preset) {
      case "18-25":
        setMinAge("18"); setMaxAge("25"); break;
      case "26-40":
        setMinAge("26"); setMaxAge("40"); break;
      case "41-60":
        setMinAge("41"); setMaxAge("60"); break;
      case "60+":
        setMinAge("60"); setMaxAge("120"); break;
    }
  };

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

  const handleCopyEpic = (e: React.MouseEvent, epic: string) => {
    e.stopPropagation();
    navigator.clipboard.writeText(epic);
    setCopiedEpic(epic);
    toast.success(`EPIC ID copied: ${epic}`);
    setTimeout(() => setCopiedEpic(null), 2000);
  };

  const handleToggleVerify = async (e: React.MouseEvent, voter: Voter) => {
    e.stopPropagation();
    try {
      const updated = await updateVoter(voter.id, { verified: !voter.verified });
      setRows((prev) => prev.map((r) => (r.id === voter.id ? updated : r)));
      toast.success(`Voter ${voter.epic} ${updated.verified ? "verified" : "marked unverified"}`);
    } catch {
      toast.error("Failed to update verification status");
    }
  };

  const handleDelete = async (id: string, name: string) => {
    if (!confirm(`Are you sure you want to delete voter record "${name}"?`)) return;
    try {
      await deleteVoter(id);
      toast.success("Voter record removed cleanly");
      void loadData();
    } catch { toast.error("Failed to delete voter record"); }
  };

  const handleBulkDelete = async () => {
    if (!confirm(`Permanently delete ${selectedIds.size} selected voter(s)?`)) return;
    try {
      const { deleted } = await bulkDeleteVoters([...selectedIds]);
      toast.success(`Successfully deleted ${deleted} voter records`);
      void loadData();
    } catch { toast.error("Bulk deletion failed"); }
  };

  const handleBulkVerify = async () => {
    try {
      let count = 0;
      for (const id of selectedIds) {
        await updateVoter(id, { verified: true });
        count++;
      }
      toast.success(`Marked ${count} voter records as Verified!`);
      void loadData();
    } catch {
      toast.error("Bulk verification completed with warnings");
    }
  };

  const handleExport = async (format: "xlsx" | "csv") => {
    setExportLoading(true);
    try {
      await downloadVoterExport(format, {
        search: search || undefined,
        gender: gender || undefined,
        relation_type: relationType || undefined,
        part_number: partNumber || undefined,
      });
      toast.success(`Export downloaded (${format.toUpperCase()})`);
    } catch (e: any) { toast.error(e?.message || "Export download failed"); }
    finally { setExportLoading(false); }
  };

  const handleJSONExport = () => {
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(rows, null, 2));
    const downloadAnchor = document.createElement('a');
    downloadAnchor.setAttribute("href", dataStr);
    downloadAnchor.setAttribute("download", `voters_export_${new Date().toISOString().slice(0, 10)}.json`);
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
    toast.success(`Downloaded ${rows.length} records as JSON`);
  };

  const pages = Math.max(1, Math.ceil(total / limit));
  const currentPage = Math.floor(offset / limit) + 1;
  const hasFilters = !!(search || gender || relationType || partNumber || constituency || houseNumber || hasPhoto || pollingStationId || isSupplement || minSerial || maxSerial || minPage || maxPage || sourceFileName || minAge || maxAge || verified || agePreset);

  const clearFilters = () => {
    setSearchInput(""); setSearch(""); setGender(""); setRelationType("");
    setPartNumber(""); setConstituency(""); setHouseNumber(""); setHasPhoto(""); setPollingStationId("");
    setIsSupplement(""); setMinSerial(""); setMaxSerial(""); setMinPage(""); setMaxPage("");
    setSourceFileName(""); setMinAge(""); setMaxAge(""); setVerified(""); setAgePreset("");
    setOffset(0);
  };

  const SortTh = ({ col, label, className = "" }: { col: SortKey; label: React.ReactNode; className?: string }) => (
    <th
      className={`px-4 py-3.5 text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300 cursor-pointer select-none hover:bg-slate-100 dark:hover:bg-slate-800/80 transition-colors ${className}`}
      onClick={() => handleSort(col)}
    >
      <div className="flex items-center space-x-1">
        <span>{label}</span>
        <SortIcon col={col} sort={sort} order={order} />
      </div>
    </th>
  );

  // Profile view fallback
  if (openVoterId) {
    return (
      <VoterProfilePage
        voterId={openVoterId}
        onBack={() => setOpenVoterId(null)}
        onNavigateVoter={setOpenVoterId}
      />
    );
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-slate-50/50 dark:bg-slate-950/50">
      
      {/* Header & Metric Cards */}
      <div className="shrink-0 px-6 py-5 border-b border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/80 backdrop-blur-md space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <div className="flex items-center space-x-3">
              <h1 className="text-2xl font-black text-slate-900 dark:text-slate-100 tracking-tight">
                Voter Directory
              </h1>
              <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-indigo-50 dark:bg-indigo-950 text-indigo-600 dark:text-indigo-400 border border-indigo-200 dark:border-indigo-800">
                {total.toLocaleString()} Records
              </span>
            </div>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
              Complete access to all 23 database columns, polling metadata, and PDF provenance.
            </p>
          </div>

          <div className="flex items-center space-x-2">
            <button
              onClick={() => setShowAiCustomizer(true)}
              className="px-3.5 py-2 rounded-xl bg-gradient-to-r from-indigo-600 via-purple-600 to-rose-600 hover:from-indigo-500 hover:to-rose-500 text-white text-xs font-black shadow-md shadow-indigo-600/30 transition-all flex items-center space-x-2 shrink-0"
            >
              <Sparkles className="w-4 h-4" />
              <span>AI Customizer</span>
            </button>
            <button
              onClick={() => { setEditingVoter(null); setIsFormOpen(true); }}
              className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold shadow-md shadow-indigo-600/20 transition-all flex items-center space-x-2 shrink-0"
            >
              <Plus className="w-4 h-4" />
              <span>Add Voter</span>
            </button>
            <div className="h-6 w-px bg-slate-200 dark:bg-slate-800 mx-1" />
            <button
              onClick={() => handleExport("xlsx")}
              disabled={exportLoading}
              className="px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-800/80 text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800 text-xs font-semibold shadow-sm transition-all flex items-center space-x-1.5"
            >
              <FileSpreadsheet className="w-4 h-4 text-emerald-600" />
              <span>Excel</span>
            </button>
            <button
              onClick={() => handleExport("csv")}
              disabled={exportLoading}
              className="px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-800/80 text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800 text-xs font-semibold shadow-sm transition-all flex items-center space-x-1.5"
            >
              <FileText className="w-4 h-4 text-blue-600" />
              <span>CSV</span>
            </button>
            <button
              onClick={handleJSONExport}
              className="px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-800/80 text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800 text-xs font-semibold shadow-sm transition-all flex items-center space-x-1.5"
            >
              <Code2 className="w-4 h-4 text-purple-600" />
              <span>JSON</span>
            </button>
          </div>
        </div>

        {/* Search & Main Action Controls */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
          <div className="relative flex-1 min-w-[280px] max-w-md">
            <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              placeholder="Search by Name, EPIC ID, House No, or Part..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              className="w-full pl-10 pr-9 py-2.5 text-xs rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500 transition-all font-medium"
            />
            {searchInput && (
              <button
                onClick={() => setSearchInput("")}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          {/* Demographic Quick Filters */}
          <div className="flex items-center space-x-1 bg-slate-100 dark:bg-slate-800/60 p-1 rounded-xl">
            {[
              { id: "", label: "All Ages" },
              { id: "18-25", label: "🎓 18-25" },
              { id: "26-40", label: "👔 26-40" },
              { id: "41-60", label: "🏢 41-60" },
              { id: "60+", label: "👴 60+" },
            ].map((preset) => (
              <button
                key={preset.id}
                onClick={() => handleAgePreset(preset.id as any)}
                className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all ${
                  agePreset === preset.id
                    ? "bg-white dark:bg-slate-900 text-indigo-600 dark:text-indigo-400 shadow-sm"
                    : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200"
                }`}
              >
                {preset.label}
              </button>
            ))}
          </div>

          {/* Categorized All 23 DB Columns Chooser Button */}
          <div className="relative">
            <button
              onClick={() => setShowColChooser(!showColChooser)}
              className="px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-300 text-xs font-semibold shadow-sm hover:bg-slate-50 transition-all flex items-center space-x-2"
            >
              <Columns3 className="w-4 h-4 text-indigo-500" />
              <span>DB Columns ({visibleCols.size}/23)</span>
            </button>

            {showColChooser && (
              <div className="absolute right-0 mt-2 w-72 p-4 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-2xl z-50 space-y-3 animate-in fade-in zoom-in-95">
                <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-2">
                  <span className="text-xs font-black uppercase tracking-wider text-slate-900 dark:text-slate-100">
                    23 Database Columns
                  </span>
                  <div className="flex items-center space-x-2">
                    <button
                      onClick={selectAllColumns}
                      className="text-[10px] font-bold text-indigo-600 hover:underline"
                    >
                      All
                    </button>
                    <button
                      onClick={resetDefaultColumns}
                      className="text-[10px] font-bold text-slate-400 hover:underline"
                    >
                      Reset
                    </button>
                  </div>
                </div>

                <div className="space-y-3 max-h-80 overflow-y-auto pr-1">
                  {CATEGORIZED_COLUMNS.map((cat) => (
                    <div key={cat.category} className="space-y-1">
                      <span className="text-[10px] font-extrabold uppercase text-indigo-600 dark:text-indigo-400 block px-1">
                        {cat.category}
                      </span>
                      <div className="grid grid-cols-1 gap-1">
                        {cat.columns.map((col) => (
                          <label
                            key={col.key}
                            className="flex items-center space-x-2.5 px-2 py-1 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-800/60 cursor-pointer text-xs font-medium text-slate-700 dark:text-slate-300"
                          >
                            <input
                              type="checkbox"
                              checked={visibleCols.has(col.key)}
                              onChange={() => toggleColumnVisibility(col.key)}
                              className="rounded border-slate-300 dark:border-slate-700 text-indigo-600 focus:ring-indigo-500"
                            />
                            <span>{col.label}</span>
                          </label>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`px-3.5 py-2.5 rounded-xl border text-xs font-semibold transition-all flex items-center space-x-2 ${
              showFilters || hasFilters
                ? "bg-indigo-50 dark:bg-indigo-950/60 border-indigo-300 dark:border-indigo-800 text-indigo-600 dark:text-indigo-400"
                : "bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-300"
            }`}
          >
            <Filter className="w-4 h-4" />
            <span>Filters</span>
            {hasFilters && (
              <span className="w-2 h-2 rounded-full bg-indigo-600 animate-pulse" />
            )}
          </button>
        </div>

        {/* Collapsible Advanced Filter Drawer */}
        {showFilters && (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3 pt-3 p-4 rounded-2xl bg-slate-100/70 dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 animate-in fade-in slide-in-from-top-2">
            <div>
              <label className="text-[11px] font-bold text-slate-500 dark:text-slate-400 block mb-1">Gender</label>
              <select
                value={gender}
                onChange={(e) => { setGender(e.target.value); setOffset(0); }}
                className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 font-medium"
              >
                <option value="">All Genders</option>
                <option value="Male">Male</option>
                <option value="Female">Female</option>
                <option value="Other">Other</option>
              </select>
            </div>

            <div>
              <label className="text-[11px] font-bold text-slate-500 dark:text-slate-400 block mb-1">Relation Type</label>
              <select
                value={relationType}
                onChange={(e) => { setRelationType(e.target.value); setOffset(0); }}
                className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 font-medium"
              >
                <option value="">All Relations</option>
                <option value="Husband">Husband</option>
                <option value="Father">Father</option>
                <option value="Mother">Mother</option>
                <option value="Other">Other / Guardian</option>
              </select>
            </div>

            <div>
              <label className="text-[11px] font-bold text-slate-500 dark:text-slate-400 block mb-1">Part Number</label>
              <input
                type="text"
                placeholder="Part No."
                value={partNumber}
                onChange={(e) => { setPartNumber(e.target.value); setOffset(0); }}
                className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 font-medium"
              />
            </div>

            <div>
              <label className="text-[11px] font-bold text-slate-500 dark:text-slate-400 block mb-1">Constituency</label>
              <input
                type="text"
                placeholder="Constituency"
                value={constituency}
                onChange={(e) => { setConstituency(e.target.value); setOffset(0); }}
                className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 font-medium"
              />
            </div>

            <div>
              <label className="text-[11px] font-bold text-slate-500 dark:text-slate-400 block mb-1">Polling Station ID</label>
              <input
                type="text"
                placeholder="Polling St. ID"
                value={pollingStationId}
                onChange={(e) => { setPollingStationId(e.target.value); setOffset(0); }}
                className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 font-medium"
              />
            </div>

            <div>
              <label className="text-[11px] font-bold text-slate-500 dark:text-slate-400 block mb-1">Roll Type</label>
              <select
                value={isSupplement}
                onChange={(e) => { setIsSupplement(e.target.value as any); setOffset(0); }}
                className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 font-medium"
              >
                <option value="">All Rolls</option>
                <option value="false">Main Roll Only</option>
                <option value="true">Supplement Only</option>
              </select>
            </div>

            <div>
              <label className="text-[11px] font-bold text-slate-500 dark:text-slate-400 block mb-1">House Number</label>
              <input
                type="text"
                placeholder="House No."
                value={houseNumber}
                onChange={(e) => { setHouseNumber(e.target.value); setOffset(0); }}
                className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 font-medium"
              />
            </div>

            <div>
              <label className="text-[11px] font-bold text-slate-500 dark:text-slate-400 block mb-1">Source PDF Name</label>
              <input
                type="text"
                placeholder="Filename.pdf"
                value={sourceFileName}
                onChange={(e) => { setSourceFileName(e.target.value); setOffset(0); }}
                className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 font-medium"
              />
            </div>

            <div>
              <label className="text-[11px] font-bold text-slate-500 dark:text-slate-400 block mb-1">Serial Range</label>
              <div className="flex items-center space-x-1">
                <input
                  type="number"
                  placeholder="Min"
                  value={minSerial}
                  onChange={(e) => { setMinSerial(e.target.value); setOffset(0); }}
                  className="w-1/2 px-2 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 font-medium"
                />
                <span className="text-xs text-slate-400">-</span>
                <input
                  type="number"
                  placeholder="Max"
                  value={maxSerial}
                  onChange={(e) => { setMaxSerial(e.target.value); setOffset(0); }}
                  className="w-1/2 px-2 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 font-medium"
                />
              </div>
            </div>

            <div>
              <label className="text-[11px] font-bold text-slate-500 dark:text-slate-400 block mb-1">Verification</label>
              <select
                value={verified}
                onChange={(e) => { setVerified(e.target.value as any); setOffset(0); }}
                className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 font-medium"
              >
                <option value="">Any Status</option>
                <option value="true">Verified Only</option>
                <option value="false">Unverified Only</option>
              </select>
            </div>
          </div>
        )}

        {/* Active Filter Badges Bar */}
        {hasFilters && (
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <span className="text-[11px] font-bold text-slate-500 dark:text-slate-400">Active Filters:</span>
            {search && (
              <span className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-indigo-50 dark:bg-indigo-950 text-indigo-600 dark:text-indigo-400 border border-indigo-200 dark:border-indigo-800 flex items-center gap-1.5">
                Search: "{search}" <X className="w-3 h-3 cursor-pointer hover:text-indigo-800" onClick={() => { setSearchInput(""); setSearch(""); }} />
              </span>
            )}
            {gender && (
              <span className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-blue-50 dark:bg-blue-950 text-blue-600 dark:text-blue-400 border border-blue-200 dark:border-blue-800 flex items-center gap-1.5">
                Gender: {gender} <X className="w-3 h-3 cursor-pointer hover:text-blue-800" onClick={() => setGender("")} />
              </span>
            )}
            {relationType && (
              <span className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-purple-50 dark:bg-purple-950 text-purple-600 dark:text-purple-400 border border-purple-200 dark:border-purple-800 flex items-center gap-1.5">
                Relation: {relationType} <X className="w-3 h-3 cursor-pointer hover:text-purple-800" onClick={() => setRelationType("")} />
              </span>
            )}
            {partNumber && (
              <span className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-700 flex items-center gap-1.5">
                Part: {partNumber} <X className="w-3 h-3 cursor-pointer hover:text-slate-900" onClick={() => setPartNumber("")} />
              </span>
            )}
            {constituency && (
              <span className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-700 flex items-center gap-1.5">
                Constituency: {constituency} <X className="w-3 h-3 cursor-pointer hover:text-slate-900" onClick={() => setConstituency("")} />
              </span>
            )}
            {pollingStationId && (
              <span className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-indigo-50 dark:bg-indigo-950 text-indigo-600 dark:text-indigo-400 border border-indigo-200 dark:border-indigo-800 flex items-center gap-1.5">
                Polling St. ID: {pollingStationId} <X className="w-3 h-3 cursor-pointer hover:text-indigo-800" onClick={() => setPollingStationId("")} />
              </span>
            )}
            {isSupplement && (
              <span className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-purple-50 dark:bg-purple-950 text-purple-600 dark:text-purple-400 border border-purple-200 dark:border-purple-800 flex items-center gap-1.5">
                {isSupplement === "true" ? "Supplement Roll Only" : "Main Roll Only"} <X className="w-3 h-3 cursor-pointer hover:text-purple-800" onClick={() => setIsSupplement("")} />
              </span>
            )}
            {houseNumber && (
              <span className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-700 flex items-center gap-1.5">
                House No: {houseNumber} <X className="w-3 h-3 cursor-pointer hover:text-slate-900" onClick={() => setHouseNumber("")} />
              </span>
            )}
            {sourceFileName && (
              <span className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-700 flex items-center gap-1.5">
                File: {sourceFileName} <X className="w-3 h-3 cursor-pointer hover:text-slate-900" onClick={() => setSourceFileName("")} />
              </span>
            )}
            {minSerial && maxSerial && (
              <span className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-amber-50 dark:bg-amber-950 text-amber-600 dark:text-amber-400 border border-amber-200 dark:border-amber-800 flex items-center gap-1.5">
                Serial: {minSerial}–{maxSerial} <X className="w-3 h-3 cursor-pointer hover:text-amber-800" onClick={() => { setMinSerial(""); setMaxSerial(""); }} />
              </span>
            )}
            {verified && (
              <span className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-emerald-50 dark:bg-emerald-950 text-emerald-600 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800 flex items-center gap-1.5">
                {verified === "true" ? "Verified Only" : "Unverified Only"} <X className="w-3 h-3 cursor-pointer hover:text-emerald-800" onClick={() => setVerified("")} />
              </span>
            )}
            <button
              onClick={clearFilters}
              className="text-xs font-bold text-rose-500 hover:text-rose-600 hover:underline ml-2"
            >
              Clear All
            </button>
          </div>
        )}
      </div>

      {/* Main Data Table Area */}
      <div className="flex-1 overflow-auto p-6">
        {loading && rows.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 gap-3">
            <Loader2 className="w-7 h-7 animate-spin text-indigo-600" />
            <p className="text-xs font-semibold text-slate-500 dark:text-slate-400">Fetching voter records...</p>
          </div>
        ) : rows.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 gap-3 bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-8 shadow-sm">
            <Users className="w-12 h-12 text-slate-300 dark:text-slate-700" />
            <p className="text-sm font-bold text-slate-700 dark:text-slate-300">No matching voter records found</p>
            {hasFilters && (
              <button onClick={clearFilters} className="text-xs font-semibold text-indigo-600 hover:underline">
                Reset active filters
              </button>
            )}
          </div>
        ) : (
          <div className="rounded-2xl border border-slate-200/80 dark:border-slate-800/80 bg-white dark:bg-slate-900 shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse whitespace-nowrap">
                <thead>
                  <tr className="border-b border-slate-200 dark:border-slate-800 bg-slate-50/80 dark:bg-slate-900/80 backdrop-blur-sm">
                    <th className="w-12 px-4 py-3.5 text-center">
                      <input
                        type="checkbox"
                        checked={selectedIds.size === rows.length && rows.length > 0}
                        onChange={toggleSelectAll}
                        className="rounded border-slate-300 dark:border-slate-700 text-indigo-600 focus:ring-indigo-500"
                      />
                    </th>
                    {visibleCols.has("serial") && <SortTh col="serial" label="S.No" className="w-16" />}
                    {visibleCols.has("epic") && <SortTh col="epic" label="EPIC ID" className="w-40" />}
                    {visibleCols.has("name") && <SortTh col="name" label="Voter Name" />}
                    {visibleCols.has("relation_type") && <th className="px-4 py-3.5 text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300">Rel. Type</th>}
                    {visibleCols.has("relation_name") && <th className="px-4 py-3.5 text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300">Relative Name</th>}
                    {visibleCols.has("house_number") && <SortTh col="house_number" label="House No" className="w-28" />}
                    {visibleCols.has("age") && <SortTh col="age" label="Age" className="w-16 text-center" />}
                    {visibleCols.has("gender") && <SortTh col="gender" label="Gender" className="w-24" />}
                    {visibleCols.has("part_number") && <SortTh col="part_number" label="Part" className="w-20 text-center" />}
                    {visibleCols.has("constituency") && <th className="px-4 py-3.5 text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300">Constituency</th>}
                    {visibleCols.has("polling_station_id") && <th className="px-4 py-3.5 text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300">Polling St. ID</th>}
                    {visibleCols.has("is_supplement") && <th className="px-4 py-3.5 text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300 text-center">Roll Type</th>}
                    {visibleCols.has("source_file_name") && <th className="px-4 py-3.5 text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300">Source File</th>}
                    {visibleCols.has("page_number") && <th className="px-4 py-3.5 text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300 text-center">Page No</th>}
                    {visibleCols.has("source_file_id") && <th className="px-4 py-3.5 text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300 font-mono">File ID</th>}
                    {visibleCols.has("source_page_id") && <th className="px-4 py-3.5 text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300 font-mono">Page ID</th>}
                    {visibleCols.has("source_record_id") && <th className="px-4 py-3.5 text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300 font-mono">Record ID</th>}
                    {visibleCols.has("verified") && <th className="w-24 px-4 py-3.5 text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300 text-center">Verification</th>}
                    {visibleCols.has("notes") && <th className="px-4 py-3.5 text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300">Notes</th>}
                    {visibleCols.has("created_at") && <th className="px-4 py-3.5 text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300">Date Added</th>}
                    {visibleCols.has("updated_at") && <th className="px-4 py-3.5 text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300">Date Updated</th>}
                    {visibleCols.has("created_by") && <th className="px-4 py-3.5 text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300">Created By</th>}
                    {visibleCols.has("updated_by") && <th className="px-4 py-3.5 text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300">Updated By</th>}
                    {visibleCols.has("actions") && <th className="w-24 px-4 py-3.5 text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300 text-center">Actions</th>}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60 text-xs">
                  {rows.map((voter) => {
                    const initials = (voter.name || "?")[0].toUpperCase();
                    const isSelected = selectedIds.has(voter.id);
                    return (
                      <tr
                        key={voter.id}
                        onClick={() => setOpenVoterId(voter.id)}
                        className={`group cursor-pointer transition-colors ${
                          isSelected
                            ? "bg-indigo-50/50 dark:bg-indigo-950/30"
                            : "hover:bg-slate-50/80 dark:hover:bg-slate-800/50"
                        }`}
                      >
                        <td className="px-4 py-3 text-center" onClick={(e) => e.stopPropagation()}>
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => toggleSelect(voter.id)}
                            className="rounded border-slate-300 dark:border-slate-700 text-indigo-600 focus:ring-indigo-500"
                          />
                        </td>

                        {visibleCols.has("serial") && (
                          <td className="px-4 py-3 font-mono font-medium text-slate-500 dark:text-slate-400">
                            {voter.serial ?? "—"}
                          </td>
                        )}

                        {visibleCols.has("epic") && (
                          <td className="px-4 py-3">
                            <button
                              onClick={(e) => handleCopyEpic(e, voter.epic)}
                              className="inline-flex items-center space-x-1.5 font-mono text-[11px] font-bold px-2.5 py-1 rounded-lg bg-indigo-50 dark:bg-indigo-950/80 text-indigo-600 dark:text-indigo-400 border border-indigo-200/80 dark:border-indigo-800/80 hover:bg-indigo-100 transition-all"
                              title="Click to copy EPIC ID"
                            >
                              <span>{voter.epic}</span>
                              {copiedEpic === voter.epic ? (
                                <Check className="w-3 h-3 text-emerald-500" />
                              ) : (
                                <Copy className="w-3 h-3 opacity-50 group-hover:opacity-100" />
                              )}
                            </button>
                          </td>
                        )}

                        {visibleCols.has("name") && (
                          <td className="px-4 py-3">
                            <div className="flex items-center space-x-3">
                              <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white font-bold text-xs shadow-sm shrink-0">
                                {initials}
                              </div>
                              <div>
                                <span
                                  onClick={(e) => { e.stopPropagation(); filterByCellValue("name", voter.name); }}
                                  title={`Click to search for "${voter.name}"`}
                                  className="font-bold text-slate-900 dark:text-slate-100 hover:text-indigo-600 dark:hover:text-indigo-400 hover:underline transition-colors block text-xs"
                                >
                                  {voter.name || "—"}
                                </span>
                              </div>
                            </div>
                          </td>
                        )}

                        {visibleCols.has("relation_type") && (
                          <td className="px-4 py-3">
                            <span
                              onClick={(e) => { e.stopPropagation(); filterByCellValue("relation_type", voter.relation_type); }}
                              className="px-2 py-0.5 rounded text-[10px] font-extrabold uppercase bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-700 hover:bg-slate-200 cursor-pointer"
                            >
                              {voter.relation_type || "—"}
                            </span>
                          </td>
                        )}

                        {visibleCols.has("relation_name") && (
                          <td className="px-4 py-3 font-medium text-slate-700 dark:text-slate-300">
                            <span
                              onClick={(e) => { e.stopPropagation(); filterByCellValue("relation_name", voter.relation_name); }}
                              className="hover:underline cursor-pointer"
                            >
                              {voter.relation_name || "—"}
                            </span>
                          </td>
                        )}

                        {visibleCols.has("house_number") && (
                          <td className="px-4 py-3">
                            <span
                              onClick={(e) => { e.stopPropagation(); filterByCellValue("house_number", voter.house_number); }}
                              title={voter.house_number ? `Click to filter by House No: ${voter.house_number}` : undefined}
                              className="font-mono font-medium text-slate-700 dark:text-slate-300 hover:text-indigo-600 dark:hover:text-indigo-400 hover:underline transition-colors cursor-pointer"
                            >
                              {voter.house_number || "—"}
                            </span>
                          </td>
                        )}

                        {visibleCols.has("age") && (
                          <td className="px-4 py-3 text-center">
                            <span
                              onClick={(e) => { e.stopPropagation(); filterByCellValue("age", voter.age); }}
                              title={voter.age ? `Click to filter by Age: ${voter.age}` : undefined}
                              className="font-extrabold text-slate-900 dark:text-slate-100 hover:text-indigo-600 dark:hover:text-indigo-400 hover:underline transition-colors cursor-pointer"
                            >
                              {voter.age ?? "—"}
                            </span>
                          </td>
                        )}

                        {visibleCols.has("gender") && (
                          <td className="px-4 py-3">
                            <GenderBadge
                              gender={voter.gender || ""}
                              onClick={(e) => { e.stopPropagation(); filterByCellValue("gender", voter.gender); }}
                            />
                          </td>
                        )}

                        {visibleCols.has("part_number") && (
                          <td className="px-4 py-3 text-center">
                            <span
                              onClick={(e) => { e.stopPropagation(); filterByCellValue("part_number", voter.part_number); }}
                              title={voter.part_number ? `Click to filter by Part No: ${voter.part_number}` : undefined}
                              className="font-mono font-semibold text-slate-600 dark:text-slate-400 hover:text-indigo-600 dark:hover:text-indigo-400 hover:underline transition-colors cursor-pointer"
                            >
                              {voter.part_number || "—"}
                            </span>
                          </td>
                        )}

                        {visibleCols.has("constituency") && (
                          <td className="px-4 py-3 font-medium text-slate-700 dark:text-slate-300">
                            <span
                              onClick={(e) => { e.stopPropagation(); filterByCellValue("constituency", voter.constituency); }}
                              className="hover:underline cursor-pointer"
                            >
                              {voter.constituency || "—"}
                            </span>
                          </td>
                        )}

                        {visibleCols.has("polling_station_id") && (
                          <td className="px-4 py-3 font-mono text-slate-600 dark:text-slate-400">
                            <span
                              onClick={(e) => { e.stopPropagation(); filterByCellValue("polling_station_id", voter.polling_station_id); }}
                              className="hover:underline cursor-pointer"
                            >
                              {voter.polling_station_id || "—"}
                            </span>
                          </td>
                        )}

                        {visibleCols.has("is_supplement") && (
                          <td className="px-4 py-3 text-center">
                            <span
                              onClick={(e) => { e.stopPropagation(); filterByCellValue("is_supplement", voter.is_supplement); }}
                              className={`px-2 py-0.5 rounded-full text-[9px] font-extrabold uppercase border cursor-pointer ${
                                voter.is_supplement
                                  ? "bg-purple-500/10 text-purple-600 border-purple-500/30"
                                  : "bg-slate-100 dark:bg-slate-800 text-slate-600 border-slate-300 dark:border-slate-700"
                              }`}
                            >
                              {voter.is_supplement ? "Supplement" : "Main Roll"}
                            </span>
                          </td>
                        )}

                        {visibleCols.has("source_file_name") && (
                          <td className="px-4 py-3 font-mono text-xs text-slate-600 dark:text-slate-400 max-w-[160px] truncate">
                            <span
                              onClick={(e) => { e.stopPropagation(); filterByCellValue("source_file_name", voter.source_file_name); }}
                              title={voter.source_file_name}
                              className="hover:underline cursor-pointer"
                            >
                              {voter.source_file_name || "—"}
                            </span>
                          </td>
                        )}

                        {visibleCols.has("page_number") && (
                          <td className="px-4 py-3 font-mono text-center text-slate-600 dark:text-slate-400">
                            {voter.page_number ?? "—"}
                          </td>
                        )}

                        {visibleCols.has("source_file_id") && (
                          <td className="px-4 py-3 font-mono text-[10px] text-slate-400">
                            {voter.source_file_id || "—"}
                          </td>
                        )}

                        {visibleCols.has("source_page_id") && (
                          <td className="px-4 py-3 font-mono text-[10px] text-slate-400">
                            {voter.source_page_id || "—"}
                          </td>
                        )}

                        {visibleCols.has("source_record_id") && (
                          <td className="px-4 py-3 font-mono text-[10px] text-slate-400">
                            {voter.source_record_id || "—"}
                          </td>
                        )}

                        {visibleCols.has("verified") && (
                          <td className="px-4 py-3 text-center" onClick={(e) => e.stopPropagation()}>
                            <button
                              onClick={(e) => handleToggleVerify(e, voter)}
                              className={`inline-flex items-center space-x-1 px-2.5 py-1 rounded-full text-[10px] font-extrabold transition-all border ${
                                voter.verified
                                  ? "bg-emerald-500/10 text-emerald-600 border-emerald-500/30"
                                  : "bg-slate-100 dark:bg-slate-800 text-slate-500 border-slate-300 dark:border-slate-700"
                              }`}
                            >
                              <BadgeCheck className={`w-3.5 h-3.5 ${voter.verified ? "text-emerald-500" : "opacity-40"}`} />
                              <span>{voter.verified ? "Verified" : "Pending"}</span>
                            </button>
                          </td>
                        )}

                        {visibleCols.has("notes") && (
                          <td className="px-4 py-3 text-slate-600 dark:text-slate-400 max-w-[160px] truncate">
                            {voter.notes || "—"}
                          </td>
                        )}

                        {visibleCols.has("created_at") && (
                          <td className="px-4 py-3 font-mono text-[11px] text-slate-500 dark:text-slate-400">
                            {voter.created_at ? new Date(voter.created_at).toLocaleDateString() : "—"}
                          </td>
                        )}

                        {visibleCols.has("updated_at") && (
                          <td className="px-4 py-3 font-mono text-[11px] text-slate-500 dark:text-slate-400">
                            {voter.updated_at ? new Date(voter.updated_at).toLocaleDateString() : "—"}
                          </td>
                        )}

                        {visibleCols.has("created_by") && (
                          <td className="px-4 py-3 text-slate-600 dark:text-slate-400">
                            {voter.created_by || "—"}
                          </td>
                        )}

                        {visibleCols.has("updated_by") && (
                          <td className="px-4 py-3 text-slate-600 dark:text-slate-400">
                            {voter.updated_by || "—"}
                          </td>
                        )}

                        {visibleCols.has("actions") && (
                          <td className="px-4 py-3 text-center" onClick={(e) => e.stopPropagation()}>
                            <div className="flex items-center justify-center space-x-1">
                              <button
                                onClick={() => setOpenVoterId(voter.id)}
                                title="View Profile"
                                className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500 hover:text-slate-900 transition-colors"
                              >
                                <Eye className="w-3.5 h-3.5" />
                              </button>
                              <button
                                onClick={() => { setEditingVoter(voter); setIsFormOpen(true); }}
                                title="Edit Record"
                                className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500 hover:text-indigo-600 transition-colors"
                              >
                                <Pencil className="w-3.5 h-3.5" />
                              </button>
                              <button
                                onClick={() => handleDelete(voter.id, voter.name || voter.epic)}
                                title="Delete Record"
                                className="p-1.5 rounded-lg hover:bg-rose-50 dark:hover:bg-rose-950/40 text-slate-400 hover:text-rose-600 transition-colors"
                              >
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          </td>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {/* Floating Multi-Select Actions Bar */}
      {selectedIds.size > 0 && (
        <div className="fixed bottom-16 left-1/2 -translate-x-1/2 px-6 py-3 rounded-2xl bg-slate-900/90 dark:bg-white/90 text-white dark:text-slate-900 shadow-2xl backdrop-blur-md flex items-center space-x-4 border border-slate-700 dark:border-slate-300 animate-in slide-in-from-bottom-5 z-50">
          <span className="text-xs font-bold px-2.5 py-1 rounded-lg bg-indigo-600 text-white">
            {selectedIds.size} Selected
          </span>
          <div className="h-4 w-px bg-slate-700 dark:bg-slate-300" />
          <button
            onClick={handleBulkVerify}
            className="text-xs font-bold flex items-center space-x-1.5 hover:text-emerald-400 transition-colors"
          >
            <UserCheck className="w-4 h-4 text-emerald-400" />
            <span>Mark Verified</span>
          </button>
          <button
            onClick={handleBulkDelete}
            className="text-xs font-bold flex items-center space-x-1.5 hover:text-rose-400 transition-colors"
          >
            <Trash2 className="w-4 h-4 text-rose-400" />
            <span>Delete Selected</span>
          </button>
          <button
            onClick={() => setSelectedIds(new Set())}
            className="p-1 rounded-lg hover:bg-slate-800 dark:hover:bg-slate-200"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Pagination Control Bar */}
      <div className="shrink-0 flex items-center justify-between px-6 py-3.5 border-t border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/80 backdrop-blur-md">
        <div className="flex items-center space-x-3 text-xs text-slate-500 dark:text-slate-400">
          <span>
            Showing <strong className="text-slate-900 dark:text-slate-100">{offset + 1}</strong>–
            <strong className="text-slate-900 dark:text-slate-100">{Math.min(offset + limit, total)}</strong> of{" "}
            <strong className="text-slate-900 dark:text-slate-100">{total.toLocaleString()}</strong> voters
          </span>
          <div className="h-4 w-px bg-slate-200 dark:border-slate-800" />
          <div className="flex items-center space-x-1">
            <span>Per Page:</span>
            <select
              value={limit}
              onChange={(e) => { setLimit(Number(e.target.value)); setOffset(0); }}
              className="px-2 py-1 text-xs font-semibold rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-slate-100"
            >
              {PAGE_SIZES.map((sz) => (
                <option key={sz} value={sz}>{sz}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="flex items-center space-x-2">
          <button
            onClick={() => setOffset((o) => Math.max(0, o - limit))}
            disabled={currentPage === 1}
            className="p-2 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-300 disabled:opacity-40 hover:bg-slate-50 transition-all"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <span className="text-xs font-bold text-slate-700 dark:text-slate-300 px-2">
            Page {currentPage} of {pages}
          </span>
          <button
            onClick={() => setOffset((o) => Math.min((pages - 1) * limit, o + limit))}
            disabled={currentPage === pages}
            className="p-2 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-300 disabled:opacity-40 hover:bg-slate-50 transition-all"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Edit Form Modal */}
      {isFormOpen && (
        <VoterFormModal
          isOpen={isFormOpen}
          voter={editingVoter ?? undefined}
          onClose={() => { setIsFormOpen(false); setEditingVoter(null); }}
          onSaved={(_v) => { setIsFormOpen(false); setEditingVoter(null); void loadData(); }}
        />
      )}

      {/* AI Customizer Modal */}
      <AiCustomizerModal
        isOpen={showAiCustomizer}
        onClose={() => setShowAiCustomizer(false)}
        onApplyTheme={handleApplyTheme}
        onApplyFilter={handleAiFilter}
        onApplyColumns={handleAiColumns}
        onTriggerExport={handleAiExport}
        onResetAll={handleAiReset}
      />
    </div>
  );
};

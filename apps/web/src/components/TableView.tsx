"use client";

import React, { useEffect, useState, useMemo } from "react";
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  createColumnHelper,
} from "@tanstack/react-table";
import {
  Check,
  RotateCcw,
  Sparkles,
  ChevronLeft,
  ChevronRight,
  Filter,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  FileSearch,
} from "lucide-react";
import { FieldValue, Record_ } from "@ocr/shared-types";
import { useOcrStore } from "@/store/useOcrStore";
import {
  fetchRecords,
  updateRecord,
  resetRecord,
  bulkUpdateRecords,
} from "@/lib/api";
import { toast } from "sonner";

const columnHelper = createColumnHelper<Record_>();

export const TableView: React.FC = () => {
  const {
    activeFileId,
    activePageId,
    searchQuery,
    onlyIssuesFilter,
    setOnlyIssuesFilter,
    onlyEditedFilter,
    setOnlyEditedFilter,
    unreviewedFilter,
    setUnreviewedFilter,
    minConfidenceFilter,
    setMinConfidenceFilter,
    refreshStats,
    hoveredRecordId,
    setHoveredRecordId,
    selectedRecordId,
    setSelectedRecordId,
    pageRefreshing,
    reocrSinglePage,
  } = useOcrStore();

  const [records, setRecords] = useState<Record_[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [pageIndex, setPageIndex] = useState(0);
  const [pageSize, setPageSize] = useState(50);
  const [isLoading, setIsLoading] = useState(false);
  const [rowSelection, setRowSelection] = useState<Record<string, boolean>>({});

  const [editingCell, setEditingCell] = useState<{ recordId: string; key: string } | null>(null);
  const [editValue, setEditValue] = useState("");

  const isCurrentPageRefreshing = activePageId ? !!pageRefreshing[activePageId] : false;

  const loadData = async () => {
    setIsLoading(true);
    try {
      const res = await fetchRecords({
        file_id: activeFileId || undefined,
        page_id: activePageId || undefined,
        search: searchQuery || undefined,
        only_issues: onlyIssuesFilter || undefined,
        only_edited: onlyEditedFilter || undefined,
        unreviewed: unreviewedFilter || undefined,
        max_confidence: minConfidenceFilter ? 0.8 : undefined,
        offset: pageIndex * pageSize,
        limit: pageSize,
      });
      setRecords(res.items);
      setTotalCount(res.total);
    } catch (e) {
      console.error(e);
      toast.error("Failed to load record rows");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [
    activeFileId,
    activePageId,
    searchQuery,
    onlyIssuesFilter,
    onlyEditedFilter,
    unreviewedFilter,
    minConfidenceFilter,
    pageIndex,
    pageSize,
  ]); // eslint-disable-line react-hooks/exhaustive-deps

  // Keyboard navigation shortcuts (J/K/Space/R)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ignore when typing inside input elements
      const target = e.target as HTMLElement;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT")) {
        return;
      }

      if (e.key === "j" || e.key === "J") {
        e.preventDefault();
        setRecords((prev) => {
          if (!prev.length) return prev;
          const currIdx = prev.findIndex((r) => r.id === selectedRecordId);
          const nextIdx = currIdx < prev.length - 1 ? currIdx + 1 : 0;
          setSelectedRecordId(prev[nextIdx].id);
          return prev;
        });
      } else if (e.key === "k" || e.key === "K") {
        e.preventDefault();
        setRecords((prev) => {
          if (!prev.length) return prev;
          const currIdx = prev.findIndex((r) => r.id === selectedRecordId);
          const prevIdx = currIdx > 0 ? currIdx - 1 : prev.length - 1;
          setSelectedRecordId(prev[prevIdx].id);
          return prev;
        });
      } else if (e.key === " " && selectedRecordId) {
        e.preventDefault();
        const targetRec = records.find((r) => r.id === selectedRecordId);
        if (targetRec) handleToggleReviewed(targetRec);
      } else if ((e.key === "r" || e.key === "R") && activePageId && !isCurrentPageRefreshing) {
        e.preventDefault();
        handleRefreshPage();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [selectedRecordId, records, activePageId, isCurrentPageRefreshing]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleRefreshPage = async () => {
    if (!activePageId) return;
    const updated = await reocrSinglePage(activePageId);
    if (updated) {
      loadData();
    }
  };

  const handleSaveCellEdit = async (recordId: string, key: string) => {
    try {
      const updated = await updateRecord(recordId, {
        edits: [{ key, value: editValue }],
      });
      setRecords((prev) => prev.map((r) => (r.id === recordId ? updated : r)));
      refreshStats(activeFileId || undefined);
      toast.success("Field value updated");
    } catch (e) {
      console.error("Save edit failed", e);
      toast.error("Failed to save field value");
    } finally {
      setEditingCell(null);
    }
  };

  const handleResetRecord = async (recordId: string) => {
    try {
      const updated = await resetRecord(recordId);
      setRecords((prev) => prev.map((r) => (r.id === recordId ? updated : r)));
      refreshStats(activeFileId || undefined);
      toast.info("Record reset to raw OCR output");
    } catch (e) {
      console.error(e);
      toast.error("Failed to reset record");
    }
  };

  const handleToggleReviewed = async (record: Record_) => {
    try {
      const updated = await updateRecord(record.id, {
        reviewed: !record.reviewed,
      });
      setRecords((prev) => prev.map((r) => (r.id === record.id ? updated : r)));
      refreshStats(activeFileId || undefined);
      if (!record.reviewed) {
        toast.success(`Record #${record.index + 1} marked as reviewed`);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleBulkAction = async (action: "approve" | "consensus" | "reset") => {
    const selectedIds = Object.keys(rowSelection).filter((id) => rowSelection[id]);
    if (!selectedIds.length) return;

    try {
      await bulkUpdateRecords({
        record_ids: selectedIds,
        reviewed: action === "approve" ? true : undefined,
        accept_suggestions: action === "consensus",
        reset_all: action === "reset",
      });
      setRowSelection({});
      loadData();
      refreshStats(activeFileId || undefined);
      toast.success(`Updated ${selectedIds.length} selected record(s)`);
    } catch (e) {
      console.error("Bulk action failed", e);
      toast.error("Bulk operation failed");
    }
  };

  const handleAcceptHighConfidence = async () => {
    const cleanHighConfIds = records
      .filter((r) => !r.reviewed && r.issues.length === 0 && (r.mean_confidence ?? 0) >= 0.85)
      .map((r) => r.id);

    if (!cleanHighConfIds.length) {
      toast.info("No unreviewed clean records (≥85% confidence) found on current page");
      return;
    }

    try {
      await bulkUpdateRecords({
        record_ids: cleanHighConfIds,
        reviewed: true,
      });
      loadData();
      refreshStats(activeFileId || undefined);
      toast.success(`Approved ${cleanHighConfIds.length} high-confidence records!`);
    } catch (e) {
      console.error(e);
      toast.error("Bulk approval failed");
    }
  };

  const renderFieldCell = (record: Record_, key: string) => {
    const field = record.fields[key];
    const val = field?.edited_value ?? field?.original_value ?? "";
    const isEdited = field?.edited_value !== null && field?.edited_value !== undefined && field?.edited_value !== field?.original_value;
    const hasSuggestion = field?.suggested_value && field.suggested_value !== val;
    const isEditing = editingCell?.recordId === record.id && editingCell?.key === key;

    if (isEditing) {
      return (
        <input
          type="text"
          autoFocus
          value={editValue}
          onChange={(e) => setEditValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") handleSaveCellEdit(record.id, key);
            if (e.key === "Escape") setEditingCell(null);
          }}
          onBlur={() => handleSaveCellEdit(record.id, key)}
          className="w-full bg-white dark:bg-slate-900 border border-indigo-500 rounded px-2 py-0.5 text-xs text-indigo-950 dark:text-indigo-200 outline-none shadow-sm font-medium"
        />
      );
    }

    return (
      <div
        onDoubleClick={() => {
          setEditingCell({ recordId: record.id, key });
          setEditValue(val);
        }}
        className="group/cell flex items-center justify-between gap-1 cursor-pointer py-0.5"
      >
        <span className={`${isEdited ? "text-amber-600 dark:text-amber-300 font-bold" : "text-slate-800 dark:text-slate-200 font-medium"}`}>
          {val || <span className="text-slate-400 dark:text-slate-600 italic">empty</span>}
        </span>

        {hasSuggestion && (
          <span
            onClick={(e) => {
              e.stopPropagation();
              updateRecord(record.id, { edits: [{ key, value: field.suggested_value ?? null }] })
                .then((updated) => {
                  setRecords((prev) => prev.map((r) => (r.id === record.id ? updated : r)));
                  refreshStats(activeFileId || undefined);
                  toast.success("Applied consensus suggestion");
                });
            }}
            className="text-[10px] px-1.5 py-0.2 rounded bg-indigo-50 dark:bg-indigo-500/20 text-indigo-600 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-500/40 hover:bg-indigo-100 dark:hover:bg-indigo-500/30 flex items-center gap-0.5"
            title={`Click to accept consensus suggestion: ${field.suggested_value}`}
          >
            <Sparkles className="w-2.5 h-2.5 text-indigo-500" />
            {field.suggested_value}
          </span>
        )}
      </div>
    );
  };

  const columns = useMemo(
    () => [
      columnHelper.display({
        id: "select",
        header: ({ table }) => (
          <input
            type="checkbox"
            checked={table.getIsAllRowsSelected()}
            onChange={table.getToggleAllRowsSelectedHandler()}
            className="rounded border-slate-300 dark:border-slate-700 text-indigo-600 focus:ring-0 cursor-pointer"
          />
        ),
        cell: ({ row }) => (
          <input
            type="checkbox"
            checked={row.getIsSelected()}
            onChange={row.getToggleSelectedHandler()}
            className="rounded border-slate-300 dark:border-slate-700 text-indigo-600 focus:ring-0 cursor-pointer"
          />
        ),
      }),
      columnHelper.accessor((r) => r.fields.serial?.edited_value ?? r.fields.serial?.original_value, {
        id: "serial",
        header: "வரிசை எண் (Serial)",
        cell: (info) => renderFieldCell(info.row.original, "serial"),
      }),
      columnHelper.accessor((r) => r.fields.epic?.edited_value ?? r.fields.epic?.original_value, {
        id: "epic",
        header: "அடையாள அட்டை எண் (EPIC ID)",
        cell: (info) => renderFieldCell(info.row.original, "epic"),
      }),
      columnHelper.accessor((r) => r.fields.name?.edited_value ?? r.fields.name?.original_value, {
        id: "name",
        header: "பெயர் (Name)",
        cell: (info) => renderFieldCell(info.row.original, "name"),
      }),
      columnHelper.accessor((r) => r.fields.relation_type?.edited_value ?? r.fields.relation_type?.original_value, {
        id: "relation_type",
        header: "உறவு முறை (Relation)",
        cell: (info) => renderFieldCell(info.row.original, "relation_type"),
      }),
      columnHelper.accessor((r) => r.fields.relation_name?.edited_value ?? r.fields.relation_name?.original_value, {
        id: "relation_name",
        header: "உறவினரின் பெயர் (Relation Name)",
        cell: (info) => renderFieldCell(info.row.original, "relation_name"),
      }),
      columnHelper.accessor((r) => r.fields.house_number?.edited_value ?? r.fields.house_number?.original_value, {
        id: "house_number",
        header: "வீட்டு எண் (House No)",
        cell: (info) => renderFieldCell(info.row.original, "house_number"),
      }),
      columnHelper.accessor((r) => r.fields.age?.edited_value ?? r.fields.age?.original_value, {
        id: "age",
        header: "வயது (Age)",
        cell: (info) => renderFieldCell(info.row.original, "age"),
      }),
      columnHelper.accessor((r) => r.fields.gender?.edited_value ?? r.fields.gender?.original_value, {
        id: "gender",
        header: "பாலினம் (Gender)",
        cell: (info) => renderFieldCell(info.row.original, "gender"),
      }),
      columnHelper.display({
        id: "issues",
        header: "பிழைகள் (Issues)",
        cell: ({ row }) => {
          const rec = row.original;
          const allIssues = [
            ...rec.issues,
            ...(Object.values(rec.fields) as FieldValue[]).flatMap((f: FieldValue) => f.issues),
          ];
          if (!allIssues.length) {
            return <span className="text-[11px] text-emerald-600 dark:text-emerald-400 font-bold flex items-center gap-1"><Check className="w-3 h-3"/>Clean</span>;
          }
          return (
            <div className="flex flex-wrap gap-1">
              {allIssues.map((issue, idx) => (
                <span
                  key={idx}
                  className={`text-[10px] px-1.5 py-0.5 rounded border font-semibold ${
                    issue.severity === "error"
                      ? "bg-rose-500/10 text-rose-600 dark:text-rose-300 border-rose-500/30"
                      : "bg-amber-500/10 text-amber-600 dark:text-amber-300 border-amber-500/30"
                  }`}
                  title={issue.message}
                >
                  {issue.code}
                </span>
              ))}
            </div>
          );
        },
      }),
      columnHelper.display({
        id: "actions",
        header: "Review",
        cell: ({ row }) => {
          const rec = row.original;
          return (
            <div className="flex items-center gap-2">
              <button
                onClick={() => handleToggleReviewed(rec)}
                className={`p-1.5 rounded transition-all ${
                  rec.reviewed
                    ? "bg-emerald-500/20 text-emerald-600 dark:text-emerald-300 border border-emerald-500/40"
                    : "bg-slate-100 dark:bg-slate-800 text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
                }`}
                title={rec.reviewed ? "Mark as unreviewed" : "Mark as reviewed (Space)"}
              >
                <Check className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={() => handleResetRecord(rec.id)}
                className="p-1.5 rounded text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800"
                title="Reset to original OCR reading"
              >
                <RotateCcw className="w-3.5 h-3.5" />
              </button>
            </div>
          );
        },
      }),
    ],
    [editingCell, editValue] // eslint-disable-line react-hooks/exhaustive-deps
  );

  const table = useReactTable({
    data: records,
    columns,
    state: { rowSelection },
    onRowSelectionChange: setRowSelection,
    getRowId: (row) => row.id,
    getCoreRowModel: getCoreRowModel(),
  });

  const selectedCount = Object.keys(rowSelection).filter((id) => rowSelection[id]).length;

  return (
    <div className="flex-1 flex flex-col h-full bg-white dark:bg-slate-950 overflow-hidden transition-colors duration-200">
      {/* Quick Filters Toolbar */}
      <div className="h-12 border-b border-slate-200 dark:border-slate-800/80 px-4 flex items-center justify-between gap-4 bg-slate-50/50 dark:bg-slate-900/40 text-xs shrink-0">
        <div className="flex items-center gap-2 overflow-x-auto">
          <span className="font-semibold text-slate-500 dark:text-slate-400 flex items-center gap-1.5 shrink-0">
            <Filter className="w-3.5 h-3.5" />
            Quick Filters:
          </span>

          <button
            onClick={() => {
              setOnlyIssuesFilter(false);
              setOnlyEditedFilter(false);
              setUnreviewedFilter(false);
              setMinConfidenceFilter(null);
            }}
            className={`px-2.5 py-1 rounded-md font-semibold transition-all ${
              !onlyIssuesFilter && !onlyEditedFilter && !unreviewedFilter && !minConfidenceFilter
                ? "bg-indigo-600 text-white shadow-sm"
                : "bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-slate-800 hover:text-slate-900 dark:hover:text-slate-200"
            }`}
          >
            All Records
          </button>

          <button
            onClick={() => setOnlyIssuesFilter(!onlyIssuesFilter)}
            className={`px-2.5 py-1 rounded-md font-semibold transition-all flex items-center gap-1 ${
              onlyIssuesFilter
                ? "bg-rose-600 text-white shadow-sm"
                : "bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-slate-800 hover:text-slate-900 dark:hover:text-slate-200"
            }`}
          >
            <AlertTriangle className="w-3 h-3" />
            Has Validation Errors
          </button>

          <button
            onClick={() => setUnreviewedFilter(!unreviewedFilter)}
            className={`px-2.5 py-1 rounded-md font-semibold transition-all ${
              unreviewedFilter
                ? "bg-amber-600 text-white shadow-sm"
                : "bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-slate-800 hover:text-slate-900 dark:hover:text-slate-200"
            }`}
          >
            Unreviewed Only
          </button>

          <button
            onClick={() => setMinConfidenceFilter(minConfidenceFilter ? null : 80)}
            className={`px-2.5 py-1 rounded-md font-semibold transition-all ${
              minConfidenceFilter
                ? "bg-indigo-600 text-white shadow-sm"
                : "bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-slate-800 hover:text-slate-900 dark:hover:text-slate-200"
            }`}
          >
            Low Confidence (&lt;80%)
          </button>
        </div>

        {/* Page-by-Page Refresh Button & Accept High Confidence */}
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={handleAcceptHighConfidence}
            className="px-3 py-1 rounded-md bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-500/40 hover:bg-emerald-100 dark:hover:bg-emerald-900/60 text-xs font-bold flex items-center gap-1.5 transition-all shadow-sm"
            title="Approve all clean records with ≥85% confidence in 1-click"
          >
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
            <span>Approve High Confidence</span>
          </button>

          {activePageId && (
            <button
              onClick={handleRefreshPage}
              disabled={isCurrentPageRefreshing}
              className="px-3 py-1 rounded-md bg-indigo-50 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-500/40 hover:bg-indigo-100 dark:hover:bg-indigo-900/60 text-xs font-bold flex items-center gap-1.5 transition-all shadow-sm disabled:opacity-50"
              title="Re-run OCR for this active page only (R)"
            >
              <RefreshCw className={`w-3.5 h-3.5 text-indigo-600 dark:text-indigo-400 ${isCurrentPageRefreshing ? "animate-spin" : ""}`} />
              <span>{isCurrentPageRefreshing ? "Refreshing Page..." : "Refresh Page (R)"}</span>
            </button>
          )}
        </div>
      </div>

      {/* Bulk Selection Bar */}
      {selectedCount > 0 && (
        <div className="bg-indigo-50 dark:bg-indigo-950/70 border-b border-indigo-200 dark:border-indigo-500/40 px-4 py-2 flex items-center justify-between text-xs animate-in fade-in slide-in-from-top-2 duration-150">
          <span className="text-indigo-900 dark:text-indigo-200 font-semibold">
            {selectedCount} record(s) selected
          </span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => handleBulkAction("approve")}
              className="px-3 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-white font-bold flex items-center gap-1 shadow-sm"
            >
              <Check className="w-3.5 h-3.5" />
              Approve Selected
            </button>
            <button
              onClick={() => handleBulkAction("consensus")}
              className="px-3 py-1 rounded bg-indigo-600 hover:bg-indigo-500 text-white font-bold flex items-center gap-1 shadow-sm"
            >
              <Sparkles className="w-3.5 h-3.5" />
              Apply Consensus
            </button>
            <button
              onClick={() => handleBulkAction("reset")}
              className="px-3 py-1 rounded bg-slate-200 dark:bg-slate-800 hover:bg-slate-300 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 font-bold flex items-center gap-1"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              Reset
            </button>
          </div>
        </div>
      )}

      {/* Main Table Content */}
      <div className="flex-1 overflow-auto">
        <table className="w-full text-left border-collapse">
          <thead className="bg-slate-100/90 dark:bg-slate-900/90 text-[11px] uppercase tracking-wider text-slate-500 dark:text-slate-400 sticky top-0 z-10 border-b border-slate-200 dark:border-slate-800 backdrop-blur-md font-bold">
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <th key={header.id} className="p-3">
                    {flexRender(header.column.columnDef.header, header.getContext())}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody className="divide-y divide-slate-200/60 dark:divide-slate-800/60 text-xs font-medium">
            {isLoading || isCurrentPageRefreshing ? (
              Array.from({ length: 6 }).map((_, i) => (
                <tr key={i} className="animate-pulse">
                  <td colSpan={columns.length} className="p-4">
                    <div className="h-4 bg-slate-200 dark:bg-slate-800 rounded w-full" />
                  </td>
                </tr>
              ))
            ) : records.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="text-center py-16 text-slate-400 dark:text-slate-500">
                  <div className="flex flex-col items-center justify-center space-y-2">
                    <FileSearch className="w-10 h-10 text-slate-300 dark:text-slate-700 stroke-[1.5]" />
                    <p className="font-semibold text-slate-600 dark:text-slate-400">No records match the current filter</p>
                    <p className="text-xs text-slate-400">Try clearing filters or search query to view all records.</p>
                  </div>
                </td>
              </tr>
            ) : (
              table.getRowModel().rows.map((row) => {
                const isHovered = hoveredRecordId === row.original.id;
                const isSelected = selectedRecordId === row.original.id;

                return (
                  <tr
                    key={row.id}
                    onMouseEnter={() => setHoveredRecordId(row.original.id)}
                    onMouseLeave={() => setHoveredRecordId(null)}
                    onClick={() => setSelectedRecordId(row.original.id)}
                    className={`transition-colors cursor-pointer ${
                      isSelected
                        ? "bg-indigo-100/70 dark:bg-indigo-950/60 font-semibold ring-1 ring-indigo-500 inset-0"
                        : isHovered
                        ? "bg-indigo-50/50 dark:bg-slate-900/60"
                        : row.original.reviewed
                        ? "bg-slate-50/50 dark:bg-slate-900/20 opacity-80"
                        : "hover:bg-slate-50 dark:hover:bg-slate-900/40"
                    }`}
                  >
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id} className="p-3">
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination & Status Footer */}
      <div className="h-12 border-t border-slate-200 dark:border-slate-800 bg-slate-50/80 dark:bg-slate-900/60 px-4 flex items-center justify-between text-xs text-slate-500 dark:text-slate-400 shrink-0">
        <div>
          Showing {records.length ? pageIndex * pageSize + 1 : 0} to{" "}
          {Math.min((pageIndex + 1) * pageSize, totalCount)} of {totalCount} records
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1">
            <span>Rows per page:</span>
            <select
              value={pageSize}
              onChange={(e) => setPageSize(Number(e.target.value))}
              className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-800 dark:text-slate-200 rounded px-2 py-1 text-xs"
            >
              {[20, 50, 100, 200].map((size) => (
                <option key={size} value={size}>
                  {size}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-1">
            <button
              onClick={() => setPageIndex((p) => Math.max(0, p - 1))}
              disabled={pageIndex === 0}
              className="p-1 rounded bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 disabled:opacity-40 text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span className="px-2 font-medium">
              Page {pageIndex + 1} of {Math.ceil(totalCount / pageSize) || 1}
            </span>
            <button
              onClick={() => setPageIndex((p) => p + 1)}
              disabled={(pageIndex + 1) * pageSize >= totalCount}
              className="p-1 rounded bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 disabled:opacity-40 text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

"use client";

/**
 * The document, rendered as the document.
 *
 * A roll page is not a table. It is a 3-column grid of bordered record
 * cells, each laid out as `serial / EPIC` above four labelled lines, and a
 * reviewer checking extraction against the scan reads far faster when the
 * two have the same shape. A flat table forces them to map column 4 back to
 * "the third line of the cell" on every row.
 *
 * So each page type renders as itself: voter grids as cells, the cover as
 * the part's details, the summary as its counts, the map sheet as its
 * photographs. Downloads stay tabular -- a spreadsheet is the right shape
 * for a spreadsheet.
 */

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  BadgeCheck,
  CheckCircle2,
  Download,
  FileText,
  ImageIcon,
  Info,
  Loader2,
  MapPin,
  RefreshCw,
  Table2,
  Trash2,
  Users,
} from "lucide-react";
import {
  Page,
  PageType,
  Photo,
  Record_,
  errorCount,
  warningCount,
} from "@ocr/shared-types";
import { useOcrStore } from "@/store/useOcrStore";
import { fetchFilePages, fetchPage, triggerDownloadExport } from "@/lib/api";
import { listPhotos, listPollingStations, promoteRecords } from "@/lib/voterApi";
import { toast } from "sonner";

interface PageSummary {
  id: string;
  page_number: number;
  status: string;
  page_type: PageType;
  classification_confidence: number;
  record_count: number;
  error_count: number;
  warning_count: number;
  template_id: string | null;
}

const PAGE_TYPE_LABELS: Record<string, string> = {
  cover_page: "Cover",
  map_photo_page: "Station imagery",
  voter_list_page: "Voter grid",
  supplement_page: "Supplement",
  summary_page: "Summary",
  legend_page: "Legend",
  blank_or_signature: "Signature",
  other: "Other",
};

const PAGE_TYPE_STYLES: Record<string, string> = {
  cover_page: "bg-blue-500/10 text-blue-400 border-blue-500/20",
  map_photo_page: "bg-teal-500/10 text-teal-400 border-teal-500/20",
  voter_list_page: "bg-indigo-500/10 text-indigo-400 border-indigo-500/20",
  supplement_page: "bg-violet-500/10 text-violet-400 border-violet-500/20",
  summary_page: "bg-amber-500/10 text-amber-400 border-amber-500/20",
  legend_page: "bg-slate-500/10 text-slate-400 border-slate-500/20",
  blank_or_signature: "bg-slate-500/10 text-slate-400 border-slate-500/20",
  other: "bg-slate-500/10 text-slate-400 border-slate-500/20",
};

/** Page types that carry voter records. Mirrors the backend's VOTER_BEARING. */
const VOTER_PAGES: PageType[] = ["voter_list_page", "supplement_page"];

/** The labels the roll itself prints inside a record cell. */
const CELL_LABELS: Record<string, string> = {
  name: "பெயர்",
  relation_name: "உறவினர்",
  house_number: "வீட்டு எண்",
  age: "வயது",
  gender: "பாலினம்",
};

function value(record: Record_, key: string): string {
  const field = record.fields?.[key];
  if (!field) return "";
  return (field.edited_value ?? field.original_value ?? "").trim();
}

function confidenceOf(record: Record_, key: string): number {
  return record.fields?.[key]?.confidence ?? 0;
}

function TypeBadge({ type }: { type: PageType }) {
  return (
    <span
      className={`px-1.5 py-0.5 rounded border text-[10px] font-medium whitespace-nowrap ${
        PAGE_TYPE_STYLES[type] ?? PAGE_TYPE_STYLES.other
      }`}
    >
      {PAGE_TYPE_LABELS[type] ?? type}
    </span>
  );
}

/**
 * One record, drawn the way the roll prints it.
 *
 * A value the extractor never found renders as a dash rather than as an
 * empty gap: on a form where every line is always printed, a blank looks
 * like the form was blank, when in fact the read failed.
 */
function RecordCell({
  record,
  index,
  onSelect,
  selected,
}: {
  record: Record_;
  index: number;
  onSelect: () => void;
  selected: boolean;
}) {
  // Derived from the record's own issues rather than read off a column:
  // `/api/pages/{id}` returns the record schema, which carries issues, not
  // the denormalised counts the records table keeps for querying.
  const errors = errorCount(record);
  const warnings = warningCount(record);
  const serial = value(record, "serial");
  const epic = value(record, "epic");
  const relationType = value(record, "relation_type");

  const rows: Array<[string, string, string]> = [
    ["name", CELL_LABELS.name, value(record, "name")],
    [
      "relation_name",
      relationType ? `${relationType}` : CELL_LABELS.relation_name,
      value(record, "relation_name"),
    ],
    ["house_number", CELL_LABELS.house_number, value(record, "house_number")],
  ];

  const border = errors
    ? "border-red-500/40 hover:border-red-500/70"
    : warnings
      ? "border-amber-500/30 hover:border-amber-500/60"
      : "border-border hover:border-primary/50";

  return (
    <button
      onClick={onSelect}
      className={`text-left rounded-lg border bg-card p-3 transition-colors ${border} ${
        selected ? "ring-2 ring-primary/60" : ""
      }`}
    >
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="px-1.5 py-0.5 rounded border border-border text-[11px] font-mono font-semibold">
          {serial || index + 1}
        </span>
        <span
          className={`text-[11px] font-mono ${
            epic ? "text-primary" : "text-red-400 italic"
          }`}
          title={epic ? `Confidence ${(confidenceOf(record, "epic") * 100).toFixed(1)}%` : undefined}
        >
          {epic || "no EPIC"}
        </span>
      </div>

      <dl className="space-y-0.5 text-[11px]">
        {rows.map(([key, label, text]) => (
          <div key={key} className="flex gap-1.5">
            <dt className="text-muted-foreground shrink-0">{label} :</dt>
            <dd className={`truncate ${text ? "" : "text-red-400 italic"}`}>
              {text || "—"}
            </dd>
          </div>
        ))}
        <div className="flex gap-3 pt-0.5">
          <div className="flex gap-1.5">
            <dt className="text-muted-foreground">{CELL_LABELS.age} :</dt>
            <dd className={value(record, "age") ? "" : "text-red-400 italic"}>
              {value(record, "age") || "—"}
            </dd>
          </div>
          <div className="flex gap-1.5 min-w-0">
            <dt className="text-muted-foreground shrink-0">{CELL_LABELS.gender} :</dt>
            <dd className={`truncate ${value(record, "gender") ? "" : "text-red-400 italic"}`}>
              {value(record, "gender") || "—"}
            </dd>
          </div>
        </div>
      </dl>

      {(errors > 0 || warnings > 0) && (
        <div className="flex items-center gap-2 mt-2 pt-2 border-t border-border text-[10px]">
          {errors > 0 && (
            <span className="text-red-400 flex items-center gap-1">
              <AlertTriangle className="w-3 h-3" /> {errors}
            </span>
          )}
          {warnings > 0 && (
            <span className="text-amber-400 flex items-center gap-1">
              <Info className="w-3 h-3" /> {warnings}
            </span>
          )}
        </div>
      )}
    </button>
  );
}

function DetailRow({ label, value: v }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex gap-3 py-1.5 border-b border-border/60 last:border-0 text-xs">
      <span className="w-44 shrink-0 text-muted-foreground">{label}</span>
      <span className="font-medium break-words">{v || "—"}</span>
    </div>
  );
}

export const DocumentView: React.FC = () => {
  const { activeFileId, setActiveFileId, files, setSelectedRecordId, selectedRecordId, deleteFile, setConfirmModal } =
    useOcrStore();

  const [pages, setPages] = useState<PageSummary[]>([]);
  const [activePage, setActivePage] = useState<PageSummary | null>(null);
  const [detail, setDetail] = useState<Page | null>(null);
  const [station, setStation] = useState<any | null>(null);
  const [photos, setPhotos] = useState<Photo[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingPage, setLoadingPage] = useState(false);
  const [promoting, setPromoting] = useState(false);
  const [downloading, setDownloading] = useState(false);

  const file = files.find((f) => f.id === activeFileId) ?? null;

  const loadPages = useCallback(async () => {
    if (!activeFileId) {
      setPages([]);
      setActivePage(null);
      return;
    }
    setLoading(true);
    try {
      const list = (await fetchFilePages(activeFileId)) as PageSummary[];
      setPages(list);
      // Open on the first page that actually holds voters; the cover is
      // rarely what someone came here to look at.
      setActivePage(list.find((p) => VOTER_PAGES.includes(p.page_type)) ?? list[0] ?? null);
    } catch {
      toast.error("Could not load pages");
    } finally {
      setLoading(false);
    }
  }, [activeFileId]);

  useEffect(() => {
    void loadPages();
  }, [loadPages]);

  useEffect(() => {
    if (!activePage) {
      setDetail(null);
      return;
    }
    setLoadingPage(true);
    fetchPage(activePage.id)
      .then(setDetail)
      .catch(() => setDetail(null))
      .finally(() => setLoadingPage(false));
  }, [activePage]);

  // Part metadata and imagery, keyed by file rather than by page.
  useEffect(() => {
    if (!activeFileId) return;
    listPollingStations({ file_id: activeFileId })
      .then((r) => setStation(r.items[0] ?? null))
      .catch(() => setStation(null));
    listPhotos({ file_id: activeFileId })
      .then((r) => setPhotos(r.items))
      .catch(() => setPhotos([]));
  }, [activeFileId]);

  const totals = useMemo(() => {
    const voterPages = pages.filter((p) => VOTER_PAGES.includes(p.page_type));
    return {
      records: voterPages.reduce((n, p) => n + p.record_count, 0),
      errors: voterPages.reduce((n, p) => n + p.error_count, 0),
      voterPages: voterPages.length,
    };
  }, [pages]);

  const reconciliation = station?.reconciliation ?? null;

  /**
   * Download the whole document as a spreadsheet.
   *
   * Scoped to the voter pages explicitly rather than to the file: a
   * file-wide export would sweep in whatever the cover and summary sheets
   * produced, and a spreadsheet of a map page's captions is not a thing
   * anyone wants.
   */
  const download = async (format: "csv" | "xlsx") => {
    const voterPageIds = pages
      .filter((p) => VOTER_PAGES.includes(p.page_type))
      .map((p) => p.id);
    if (voterPageIds.length === 0) {
      toast.error("This document has no voter pages to export");
      return;
    }
    setDownloading(true);
    try {
      await triggerDownloadExport({
        format,
        mode: "all",
        file_ids: [],
        page_ids: voterPageIds,
        record_ids: [],
        include_page_numbers: true,
        include_confidence: false,
        include_issues: false,
      });
    } catch (e: any) {
      toast.error(e?.message || "Export failed");
    } finally {
      setDownloading(false);
    }
  };

  const approve = async (onlyClean: boolean) => {
    if (!activeFileId) return;
    setPromoting(true);
    try {
      const result = await promoteRecords({
        file_id: activeFileId,
        only_clean: onlyClean,
        on_conflict: "skip",
      });
      const parts = [`${result.created} added`];
      if (result.updated) parts.push(`${result.updated} updated`);
      if (result.skipped) parts.push(`${result.skipped} skipped`);
      toast.success(`Stored in the voter database: ${parts.join(", ")}`);
      await loadPages();
      refreshStats(activeFileId || undefined);
    } catch (e: any) {
      toast.error(e?.message || "Could not store these records");
    } finally {
      setPromoting(false);
    }
  };

  if (!activeFileId) {
    return (
      <div className="flex-1 flex items-center justify-center text-sm text-muted-foreground">
        Select a document to view its contents.
      </div>
    );
  }

  return (
    <div className="flex-1 flex overflow-hidden min-w-0">
      {/* Page rail ------------------------------------------------------- */}
      <aside className="w-52 shrink-0 border-r border-border overflow-y-auto bg-card/30">
        <div className="px-3 py-2.5 border-b border-border sticky top-0 bg-card/95 backdrop-blur space-y-1.5">
          <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
            Document
          </div>
          {/* The view is useless without a way to pick which document it is
              showing, and the sidebar's file list collapses on narrow
              viewports. Keep the choice where the pages are. */}
          <select
            value={activeFileId ?? ""}
            onChange={(e) => setActiveFileId(e.target.value)}
            className="w-full bg-background border border-border rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-primary"
            title={file?.name}
          >
            {files.map((f) => (
              <option key={f.id} value={f.id}>
                {f.name.length > 28 ? `${f.name.slice(0, 26)}…` : f.name}
                {f.status === "completed" ? "" : ` (${f.status})`}
              </option>
            ))}
          </select>
          <div className="text-[10px] uppercase tracking-wide text-muted-foreground pt-1">
            Pages
          </div>
        </div>
        {loading ? (
          <div className="p-4 flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading…
          </div>
        ) : (
          <ul className="p-2 space-y-1">
            {pages.map((p) => (
              <li key={p.id}>
                <button
                  onClick={() => setActivePage(p)}
                  className={`w-full text-left px-2.5 py-2 rounded-lg transition-colors ${
                    activePage?.id === p.id
                      ? "bg-primary/10 border border-primary/30"
                      : "hover:bg-muted/60 border border-transparent"
                  }`}
                >
                  <div className="flex items-center justify-between gap-1.5">
                    <span className="text-xs font-semibold">Page {p.page_number}</span>
                    {p.error_count > 0 && (
                      <span className="text-[10px] text-red-400">{p.error_count}</span>
                    )}
                  </div>
                  <div className="mt-1 flex items-center gap-1.5 flex-wrap">
                    <TypeBadge type={p.page_type} />
                    {p.record_count > 0 && (
                      <span className="text-[10px] text-muted-foreground">
                        {p.record_count} rec
                      </span>
                    )}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </aside>

      {/* Body ------------------------------------------------------------ */}
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        {/* Approval bar */}
        <div className="border-b border-border px-4 py-2.5 flex items-center gap-3 flex-wrap bg-card/40">
          <div className="flex items-center gap-2 text-xs">
            <Users className="w-3.5 h-3.5 text-muted-foreground" />
            <span className="font-semibold">{totals.records}</span>
            <span className="text-muted-foreground">
              records across {totals.voterPages} voter page
              {totals.voterPages === 1 ? "" : "s"}
            </span>
            {totals.errors > 0 && (
              <span className="text-red-400 flex items-center gap-1">
                <AlertTriangle className="w-3 h-3" />
                {totals.errors} need review
              </span>
            )}
          </div>

          {reconciliation && (
            <span
              className={`px-2 py-0.5 rounded border text-[11px] font-medium flex items-center gap-1 ${
                reconciliation.reconciled
                  ? "bg-green-500/10 text-green-400 border-green-500/20"
                  : "bg-red-500/10 text-red-400 border-red-500/20"
              }`}
              title="Extracted records compared with the total the roll itself prints"
            >
              {reconciliation.reconciled ? (
                <CheckCircle2 className="w-3 h-3" />
              ) : (
                <AlertTriangle className="w-3 h-3" />
              )}
              {reconciliation.extracted_records} of {reconciliation.printed_total} printed
            </span>
          )}

          <div className="ml-auto flex items-center gap-2">
            <button
              onClick={() => {
                if (!activeFileId || !file) return;
                setConfirmModal({
                  isOpen: true,
                  title: "Delete Document?",
                  message: `Are you sure you want to delete "${file.name}"? All associated page extractions, OCR blocks, and voter records will be permanently removed from the system.`,
                  danger: true,
                  confirmText: "Delete Document",
                  onConfirm: async () => {
                    await deleteFile(activeFileId);
                  },
                });
              }}
              className="px-2.5 py-1.5 rounded-lg border border-rose-500/30 text-rose-600 dark:text-rose-400 hover:bg-rose-500/10 text-xs flex items-center gap-1.5 font-medium transition-colors"
              title="Permanently delete this document and its extracted voter records"
            >
              <Trash2 className="w-3.5 h-3.5" /> Delete
            </button>
            <button
              onClick={() => void loadPages()}
              className="px-2.5 py-1.5 rounded-lg border border-border hover:bg-muted text-xs flex items-center gap-1.5"
            >
              <RefreshCw className="w-3.5 h-3.5" /> Refresh
            </button>
            <button
              onClick={() => void download("csv")}
              disabled={downloading || totals.records === 0}
              className="px-2.5 py-1.5 rounded-lg border border-border hover:bg-muted text-xs flex items-center gap-1.5 disabled:opacity-40"
              title="Download every record in this document as a spreadsheet, in the roll's column order"
            >
              {downloading ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Table2 className="w-3.5 h-3.5" />
              )}
              CSV
            </button>
            <button
              onClick={() => void download("xlsx")}
              disabled={downloading || totals.records === 0}
              className="px-2.5 py-1.5 rounded-lg border border-border hover:bg-muted text-xs flex items-center gap-1.5 disabled:opacity-40"
              title="Download every record in this document as a spreadsheet, in the roll's column order"
            >
              <Download className="w-3.5 h-3.5" /> Excel
            </button>
            <button
              onClick={() => void approve(true)}
              disabled={promoting || totals.records === 0}
              className="px-3 py-1.5 rounded-lg bg-primary text-primary-foreground hover:opacity-90 disabled:opacity-40 text-xs font-semibold flex items-center gap-1.5"
              title="Store the records with no validation errors in the voter database"
            >
              {promoting ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <BadgeCheck className="w-3.5 h-3.5" />
              )}
              Approve clean records
            </button>
            {totals.errors > 0 && (
              <button
                onClick={() => void approve(false)}
                disabled={promoting}
                className="px-2.5 py-1.5 rounded-lg border border-border hover:bg-muted text-xs disabled:opacity-40"
                title="Store every record, including those with validation errors"
              >
                Approve all
              </button>
            )}
          </div>
        </div>

        {/* Page body */}
        <div className="flex-1 overflow-y-auto p-4">
          {loadingPage ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="w-4 h-4 animate-spin" /> Loading page…
            </div>
          ) : !activePage || !detail ? (
            <div className="text-sm text-muted-foreground">No page selected.</div>
          ) : (
            <>
              <div className="flex items-center gap-2 mb-3">
                <h2 className="text-sm font-bold">Page {activePage.page_number}</h2>
                <TypeBadge type={activePage.page_type} />
                {activePage.classification_confidence > 0 && (
                  <span className="text-[10px] text-muted-foreground">
                    classified {(activePage.classification_confidence * 100).toFixed(0)}%
                  </span>
                )}
              </div>

              {VOTER_PAGES.includes(activePage.page_type) ? (
                detail.records.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    No records extracted from this page.
                  </p>
                ) : (
                  <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-2.5">
                    {detail.records.map((r, i) => (
                      <RecordCell
                        key={r.id}
                        record={r}
                        index={i}
                        selected={selectedRecordId === r.id}
                        onSelect={() => setSelectedRecordId(r.id)}
                      />
                    ))}
                  </div>
                )
              ) : activePage.page_type === "cover_page" ? (
                <CoverPanel station={station} />
              ) : activePage.page_type === "summary_page" ? (
                <SummaryPanel station={station} />
              ) : activePage.page_type === "map_photo_page" ? (
                <PhotoPanel photos={photos} />
              ) : (
                <TextPanel page={detail} />
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};

function CoverPanel({ station }: { station: any | null }) {
  if (!station) {
    return (
      <p className="text-sm text-muted-foreground">
        Part details have not been extracted for this document yet. They are read
        when extraction finishes.
      </p>
    );
  }
  const d = station.details ?? {};
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 max-w-5xl">
      <section className="card-vimc p-4">
        <h3 className="text-xs font-bold uppercase tracking-wide text-muted-foreground mb-3 flex items-center gap-1.5">
          <FileText className="w-3.5 h-3.5" /> Constituency
        </h3>
        <DetailRow label="Assembly constituency" value={`${station.ac_number}-${station.ac_name}`} />
        <DetailRow label="Parliamentary constituency" value={`${station.pc_number}-${station.pc_name}`} />
        <DetailRow label="Part number" value={station.part_number} />
        <DetailRow label="Revision" value={d.revision_type} />
        <DetailRow label="Qualifying date" value={d.qualifying_date} />
        <DetailRow label="Published" value={d.publication_date} />
      </section>

      <section className="card-vimc p-4">
        <h3 className="text-xs font-bold uppercase tracking-wide text-muted-foreground mb-3 flex items-center gap-1.5">
          <MapPin className="w-3.5 h-3.5" /> Polling station
        </h3>
        <DetailRow label="Station" value={`${station.station_number} — ${station.name}`} />
        <DetailRow label="Address" value={station.address} />
        <DetailRow label="Type" value={station.station_type} />
        <DetailRow label="Section" value={station.section_details} />
      </section>

      <section className="card-vimc p-4">
        <h3 className="text-xs font-bold uppercase tracking-wide text-muted-foreground mb-3">
          Location
        </h3>
        <DetailRow label="Main town / village" value={d.main_town} />
        <DetailRow label="Post office" value={d.post_office} />
        <DetailRow label="Police station" value={d.police_station} />
        <DetailRow label="Panchayat" value={d.panchayat} />
        <DetailRow label="Taluk" value={station.taluk} />
        <DetailRow label="District" value={station.district} />
        <DetailRow label="PIN code" value={station.pincode} />
      </section>

      <section className="card-vimc p-4">
        <h3 className="text-xs font-bold uppercase tracking-wide text-muted-foreground mb-3">
          Electors as printed
        </h3>
        <DetailRow label="Serial range" value={`${station.serial_start} – ${station.serial_end}`} />
        <DetailRow label="Male" value={station.male_electors} />
        <DetailRow label="Female" value={station.female_electors} />
        <DetailRow label="Third gender" value={station.third_gender_electors} />
        <DetailRow label="Total" value={<strong>{station.total_electors}</strong>} />
      </section>
    </div>
  );
}

function SummaryPanel({ station }: { station: any | null }) {
  const r = station?.reconciliation;
  if (!r) {
    return (
      <p className="text-sm text-muted-foreground">
        No summary extracted for this document.
      </p>
    );
  }
  return (
    <div className="max-w-2xl space-y-4">
      <section className="card-vimc p-4">
        <h3 className="text-xs font-bold uppercase tracking-wide text-muted-foreground mb-3">
          How the roll reaches its total
        </h3>
        <DetailRow label="Base roll" value={r.base_total} />
        <DetailRow label="Additions (supplement)" value={`+ ${r.additions_total}`} />
        <DetailRow label="Deletions" value={`− ${r.deletions_total}`} />
        <DetailRow label="Net total printed" value={<strong>{r.printed_total}</strong>} />
        <DetailRow label="Corrections" value={r.corrections} />
      </section>

      <section
        className={`card-vimc p-4 border ${
          r.reconciled ? "border-green-500/30" : "border-red-500/30"
        }`}
      >
        <h3 className="text-xs font-bold uppercase tracking-wide text-muted-foreground mb-3">
          Extraction against the printed total
        </h3>
        <DetailRow label="Records extracted" value={r.extracted_records} />
        <DetailRow label="Printed total" value={r.printed_total} />
        <DetailRow
          label="Difference"
          value={
            <span className={r.reconciled ? "text-green-400" : "text-red-400"}>
              {r.difference > 0 ? `+${r.difference}` : r.difference}
              {r.reconciled ? " — reconciled" : " — needs investigation"}
            </span>
          }
        />
      </section>
    </div>
  );
}

function PhotoPanel({ photos }: { photos: Photo[] }) {
  const station = photos.filter((p) => p.photo_type !== "voter_crop");
  if (station.length === 0) {
    return (
      <p className="text-sm text-muted-foreground flex items-center gap-2">
        <ImageIcon className="w-4 h-4" /> No imagery extracted from this page.
      </p>
    );
  }
  const labels: Record<string, string> = {
    nazri_naksha: "Locality sketch (Nazri Naksha)",
    google_map: "Satellite view",
    station_building: "Station building",
    station_front: "Station frontage",
    cad_map: "Floor plan",
    key_map: "Route map",
  };
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4 max-w-5xl">
      {station.map((p) => (
        <figure key={p.id} className="rounded-xl border border-border overflow-hidden bg-muted/30">
          <img
            src={p.url}
            alt={labels[p.photo_type] ?? p.photo_type}
            className="w-full h-44 object-contain bg-background"
            loading="lazy"
          />
          <figcaption className="px-3 py-2 text-[11px] font-medium border-t border-border">
            {labels[p.photo_type] ?? p.photo_type}
            <span className="text-muted-foreground font-normal ml-1">
              {p.width}×{p.height}
            </span>
          </figcaption>
        </figure>
      ))}
    </div>
  );
}

function TextPanel({ page }: { page: Page }) {
  if (!page.lines.length) {
    return <p className="text-sm text-muted-foreground">No text on this page.</p>;
  }
  return (
    <div className="card-vimc p-4 max-w-3xl">
      <h3 className="text-xs font-bold uppercase tracking-wide text-muted-foreground mb-3">
        Recognised text
      </h3>
      <div className="space-y-1 text-xs leading-relaxed">
        {page.lines.map((l) => (
          <p key={l.id}>{l.text}</p>
        ))}
      </div>
    </div>
  );
}

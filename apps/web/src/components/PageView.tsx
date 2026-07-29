"use client";

import React, { useEffect, useState } from "react";
import {
  ZoomIn,
  ZoomOut,
  Maximize2,
  RefreshCw,
  Eye,
  Layers,
  AlertTriangle,
  CheckCircle,
  Table as TableIcon,
} from "lucide-react";
import { BBox, FieldValue, Issue, OcrLine, Page, Record_ } from "@ocr/shared-types";
import { useOcrStore } from "@/store/useOcrStore";
import { fetchPage } from "@/lib/api";

const FIELD_TAMIL_LABELS: Record<string, string> = {
  serial: "வரிசை எண் (S.No)",
  epic: "அடையாள அட்டை எண் (EPIC ID)",
  name: "பெயர் (Name)",
  relation_type: "உறவு முறை (Relation)",
  relation_name: "உறவினரின் பெயர் (Relation Name)",
  house_number: "வீட்டு எண் (House No)",
  age: "வயது (Age)",
  gender: "பாலினம் (Gender)",
};

export const PageView: React.FC = () => {
  const {
    activePageId,
    hoveredRecordId,
    setHoveredRecordId,
    selectedRecordId,
    setSelectedRecordId,
    setActiveTab,
    pageRefreshing,
    reocrSinglePage,
  } = useOcrStore();

  const [page, setPage] = useState<Page | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [showCells, setShowCells] = useState(true);
  const [showLines, setShowLines] = useState(false);
  const [zoom, setZoom] = useState(1.0);
  const [upscaleParam, setUpscaleParam] = useState(2.0);

  const isRefreshing = activePageId ? !!pageRefreshing[activePageId] : false;

  const loadPageData = async () => {
    if (!activePageId) return;
    setIsLoading(true);
    try {
      const data = await fetchPage(activePageId);
      setPage(data);
      if (data.records.length > 0 && !selectedRecordId) {
        setSelectedRecordId(data.records[0].id);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadPageData();
  }, [activePageId]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleRefreshPage = async () => {
    if (!activePageId) return;
    const updated = await reocrSinglePage(activePageId, page?.template_id || "auto", upscaleParam);
    if (updated) {
      setPage(updated);
    }
  };

  if (!activePageId) {
    return (
      <div className="flex-1 flex items-center justify-center text-slate-400 dark:text-slate-500 text-sm bg-white dark:bg-slate-950">
        Select a page from the sidebar to inspect geometry & OCR bounding boxes.
      </div>
    );
  }

  if (isLoading || !page) {
    return (
      <div className="flex-1 flex items-center justify-center text-slate-400 dark:text-slate-500 text-sm bg-white dark:bg-slate-950 animate-pulse">
        <div className="flex items-center gap-2">
          <RefreshCw className="w-4 h-4 animate-spin text-indigo-500" />
          <span>Loading page geometry & canvas...</span>
        </div>
      </div>
    );
  }

  const selectedRecord = page.records.find((r: Record_) => r.id === selectedRecordId);

  return (
    <div className="flex-1 flex h-full bg-white dark:bg-slate-950 overflow-hidden transition-colors duration-200">
      {/* Left Canvas: Interactive Image Viewer */}
      <div className="flex-1 flex flex-col border-r border-slate-200 dark:border-slate-800 relative">
        {/* Controls Toolbar */}
        <div className="h-11 border-b border-slate-200 dark:border-slate-800 bg-slate-50/80 dark:bg-slate-900/60 px-4 flex items-center justify-between text-xs z-10 backdrop-blur-md">
          <div className="flex items-center gap-3">
            <span className="font-semibold text-slate-800 dark:text-slate-200">
              Page {page.page_number} ({page.width}x{page.height}px)
            </span>
            <span className="text-slate-400 dark:text-slate-500">OCR: {page.ocr_ms}ms</span>
          </div>

          <div className="flex items-center gap-2.5">
            <button
              onClick={() => setShowCells(!showCells)}
              className={`px-2.5 py-1 rounded border flex items-center gap-1 font-semibold transition-all ${
                showCells
                  ? "bg-amber-50 dark:bg-amber-500/20 text-amber-700 dark:text-amber-300 border-amber-300 dark:border-amber-500/40 shadow-sm"
                  : "bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-800 text-slate-500 dark:text-slate-400"
              }`}
            >
              <Layers className="w-3.5 h-3.5" />
              Cells Grid (3x10)
            </button>

            <button
              onClick={() => setShowLines(!showLines)}
              className={`px-2.5 py-1 rounded border flex items-center gap-1 font-semibold transition-all ${
                showLines
                  ? "bg-emerald-50 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-300 border-emerald-300 dark:border-emerald-500/40 shadow-sm"
                  : "bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-800 text-slate-500 dark:text-slate-400"
              }`}
            >
              <Eye className="w-3.5 h-3.5" />
              OCR BBoxes
            </button>

            <div className="h-4 w-px bg-slate-200 dark:bg-slate-800 mx-1" />

            {/* Page-by-Page Refresh Button */}
            <button
              onClick={handleRefreshPage}
              disabled={isRefreshing}
              className="px-3 py-1 rounded bg-indigo-600 hover:bg-indigo-500 text-white font-bold flex items-center gap-1.5 shadow-sm text-xs transition-all disabled:opacity-50"
              title="Re-run OCR for this page only (Shortcut: R)"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? "animate-spin" : ""}`} />
              <span>{isRefreshing ? "Refreshing..." : "Refresh Page (R)"}</span>
            </button>

            <div className="h-4 w-px bg-slate-200 dark:bg-slate-800 mx-1" />

            {/* Zoom Controls */}
            <div className="flex items-center gap-1">
              <button
                onClick={() => setZoom((z) => Math.max(0.5, z - 0.2))}
                className="p-1 rounded bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
                title="Zoom Out"
              >
                <ZoomOut className="w-3.5 h-3.5" />
              </button>
              <span className="w-12 text-center font-mono text-[11px] text-slate-500 dark:text-slate-400">
                {(zoom * 100).toFixed(0)}%
              </span>
              <button
                onClick={() => setZoom((z) => Math.min(2.5, z + 0.2))}
                className="p-1 rounded bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
                title="Zoom In"
              >
                <ZoomIn className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={() => setZoom(1.0)}
                className="p-1 rounded bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
                title="Fit 100%"
              >
                <Maximize2 className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>

        {/* Image Canvas */}
        <div className="flex-1 overflow-auto p-4 flex items-center justify-center bg-slate-100/50 dark:bg-slate-900/30 relative">
          {page.image_path ? (
            <div
              className={`relative inline-block shadow-2xl rounded border border-slate-300 dark:border-slate-800 transition-all ${
                isRefreshing ? "opacity-40 pointer-events-none" : ""
              }`}
              style={{ transform: `scale(${zoom})`, transformOrigin: "center center" }}
            >
              <img
                src={`/api/pages/${page.id}/image`}
                alt={`Page ${page.page_number}`}
                className="max-w-none block rounded"
              />

              {/* SVG Overlay */}
              <svg
                className="absolute inset-0 w-full h-full pointer-events-auto"
                viewBox={`0 0 ${Number.isFinite(Number(page.width)) && Number(page.width) > 0 ? Number(page.width) : 1000} ${Number.isFinite(Number(page.height)) && Number(page.height) > 0 ? Number(page.height) : 1000}`}
              >
                {/* Cell Rectangles */}
                {showCells &&
                  page.layout?.cells.map((cell: BBox, idx: number) => {
                    const record = page.records[idx];
                    const isSelected = record?.id === selectedRecordId;
                    const isHovered = record?.id === hoveredRecordId;

                    const cx = Number.isFinite(Number(cell?.x)) ? Number(cell.x) : 0;
                    const cy = Number.isFinite(Number(cell?.y)) ? Number(cell.y) : 0;
                    const cw = Number.isFinite(Number(cell?.w)) && Number(cell.w) >= 0 ? Number(cell.w) : 0;
                    const ch = Number.isFinite(Number(cell?.h)) && Number(cell.h) >= 0 ? Number(cell.h) : 0;

                    return (
                      <g key={idx}>
                        <rect
                          x={cx}
                          y={cy}
                          width={cw}
                          height={ch}
                          fill={
                            isSelected
                              ? "rgba(99, 102, 241, 0.3)"
                              : isHovered
                              ? "rgba(99, 102, 241, 0.15)"
                              : "rgba(245, 158, 11, 0.05)"
                          }
                          stroke={isSelected ? "#4f46e5" : isHovered ? "#6366f1" : "#f59e0b"}
                          strokeWidth={isSelected ? 3.5 : isHovered ? 2.5 : 1.5}
                          strokeDasharray={isSelected || isHovered ? undefined : "4 2"}
                          className="cursor-pointer transition-all hover:fill-indigo-500/20"
                          onMouseEnter={() => record && setHoveredRecordId(record.id)}
                          onMouseLeave={() => setHoveredRecordId(null)}
                          onClick={() => record && setSelectedRecordId(record.id)}
                          onDoubleClick={() => {
                            if (record) {
                              setSelectedRecordId(record.id);
                              setActiveTab("table");
                            }
                          }}
                        />
                        <text
                          x={cx + 8}
                          y={cy + 20}
                          fill={isSelected ? "#4f46e5" : isHovered ? "#6366f1" : "#f59e0b"}
                          fontSize="16"
                          fontWeight="bold"
                          className="pointer-events-none select-none drop-shadow"
                        >
                          #{idx + 1}
                        </text>
                      </g>
                    );
                  })}

                {/* OCR Lines Bounding Boxes */}
                {showLines &&
                  page.lines.map((ln: OcrLine) => {
                    const lx = Number.isFinite(Number(ln?.bbox?.x)) ? Number(ln.bbox.x) : 0;
                    const ly = Number.isFinite(Number(ln?.bbox?.y)) ? Number(ln.bbox.y) : 0;
                    const lw = Number.isFinite(Number(ln?.bbox?.w)) && Number(ln.bbox.w) >= 0 ? Number(ln.bbox.w) : 0;
                    const lh = Number.isFinite(Number(ln?.bbox?.h)) && Number(ln.bbox.h) >= 0 ? Number(ln.bbox.h) : 0;

                    return (
                      <rect
                        key={ln.id}
                        x={lx}
                        y={ly}
                        width={lw}
                        height={lh}
                        fill="none"
                        stroke={ln.confidence >= 0.7 ? "#10b981" : "#f43f5e"}
                        strokeWidth={1}
                        className="pointer-events-none"
                      />
                    );
                  })}
              </svg>
            </div>
          ) : (
            <div className="text-slate-400 text-sm">Page image render unavailable</div>
          )}

          {/* Refresh Loading Overlay */}
          {isRefreshing && (
            <div className="absolute inset-0 bg-white/60 dark:bg-slate-950/60 backdrop-blur-xs flex flex-col items-center justify-center z-20 space-y-2">
              <RefreshCw className="w-8 h-8 text-indigo-600 dark:text-indigo-400 animate-spin" />
              <p className="text-xs font-bold text-slate-800 dark:text-slate-200">Re-processing page {page.page_number}...</p>
            </div>
          )}
        </div>

        {/* Footer Upscale Config */}
        <div className="h-10 border-t border-slate-200 dark:border-slate-800 bg-slate-50/80 dark:bg-slate-900/80 px-4 flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
          <div className="truncate max-w-xl">
            <span className="font-semibold text-slate-700 dark:text-slate-300">Header: </span>
            {page.header_text || "None"}
          </div>
          <div className="flex items-center gap-2">
            <span>Upscale DPI multiplier:</span>
            <input
              type="range"
              min="1.0"
              max="5.0"
              step="0.5"
              value={upscaleParam}
              onChange={(e) => setUpscaleParam(parseFloat(e.target.value))}
              className="w-16 h-1 bg-slate-300 dark:bg-slate-700 rounded appearance-none"
            />
            <span className="font-bold">{upscaleParam}x</span>
          </div>
        </div>
      </div>

      {/* Right Side Inspector Panel */}
      <div className="w-80 border-l border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950 flex flex-col shrink-0">
        <div className="p-3 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60 font-bold text-xs text-slate-800 dark:text-slate-200 flex items-center justify-between">
          <span>Record Inspector</span>
          {selectedRecord ? (
            <div className="flex items-center gap-2">
              <span className="text-indigo-600 dark:text-indigo-400 font-mono text-xs font-bold">
                #{selectedRecord.index + 1}
              </span>
              <button
                onClick={() => setActiveTab("table")}
                className="px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800 hover:bg-indigo-50 text-[10px] text-slate-600 dark:text-slate-300 flex items-center gap-1"
                title="Jump to row in Table View"
              >
                <TableIcon className="w-3 h-3" />
                Table
              </button>
            </div>
          ) : null}
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {selectedRecord ? (
            <>
              {/* Record Summary Box */}
              <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-3.5 space-y-2 text-xs shadow-sm">
                <div className="flex items-center justify-between">
                  <span className="text-slate-500 dark:text-slate-400 font-medium">Confidence:</span>
                  <span className="font-bold text-emerald-600 dark:text-emerald-400">
                    {((selectedRecord.mean_confidence ?? 0) * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500 dark:text-slate-400 font-medium">Status:</span>
                  <span
                    className={`font-bold flex items-center gap-1 ${
                      selectedRecord.reviewed
                        ? "text-emerald-600 dark:text-emerald-400"
                        : "text-amber-600 dark:text-amber-400"
                    }`}
                  >
                    {selectedRecord.reviewed ? <CheckCircle className="w-3.5 h-3.5"/> : null}
                    {selectedRecord.reviewed ? "Reviewed" : "Unreviewed"}
                  </span>
                </div>
              </div>

              {/* Issues for this Record */}
              {selectedRecord.issues.length > 0 && (
                <div className="space-y-1.5">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-rose-600 dark:text-rose-400">
                    Record Validation Issues
                  </span>
                  {selectedRecord.issues.map((issue: Issue, idx: number) => (
                    <div
                      key={idx}
                      className="p-2.5 rounded-lg bg-rose-50 dark:bg-rose-500/10 border border-rose-200 dark:border-rose-500/30 text-rose-700 dark:text-rose-300 text-xs flex items-start gap-2"
                    >
                      <AlertTriangle className="w-4 h-4 text-rose-500 flex-shrink-0 mt-0.5" />
                      <div>
                        <div className="font-bold">{issue.code}</div>
                        <div className="text-[11px] opacity-90 mt-0.5">{issue.message}</div>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Extracted Fields */}
              <div className="space-y-3">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Extracted Voter Fields
                </span>

                {(Object.values(selectedRecord.fields) as FieldValue[]).map((field: FieldValue) => (
                  <div
                    key={field.key}
                    className="p-3 rounded-xl bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 space-y-1 shadow-sm"
                  >
                    <div className="flex items-center justify-between text-[11px]">
                      <span className="font-semibold text-slate-600 dark:text-slate-400">
                        {FIELD_TAMIL_LABELS[field.key] || field.key}
                      </span>
                      <span className="text-slate-400 font-mono text-[10px]">
                        {(field.confidence * 100).toFixed(0)}%
                      </span>
                    </div>

                    <div className="text-xs font-bold text-slate-900 dark:text-slate-100">
                      {field.edited_value ?? field.original_value ?? (
                        <span className="text-slate-400 italic">empty</span>
                      )}
                    </div>

                    {field.edited_value !== null && field.edited_value !== field.original_value && (
                      <div className="text-[10px] text-amber-600 dark:text-amber-400 font-medium italic">
                        Original: {field.original_value}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="text-center py-12 text-slate-400 text-xs">
              Hover or click a record cell on the page canvas to inspect its extracted fields.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

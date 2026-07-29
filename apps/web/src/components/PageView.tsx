import React, { useState } from "react";
import { useOcrStore } from "@/store/useOcrStore";
import { BBox, OcrLine } from "@ocr/shared-types";
import {
  ZoomIn,
  ZoomOut,
  RotateCw,
  Eye,
  CheckCircle2,
  AlertTriangle,
  FileText,
  ChevronLeft,
  ChevronRight,
  Layers,
  Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";

export function PageView() {
  const { selectedFile, activePage, pages, setActivePage, setActiveTab } = useOcrStore();
  const [zoom, setZoom] = useState(1);
  const [showCells, setShowCells] = useState(true);
  const [showLines, setShowLines] = useState(true);
  const [stage, setStage] = useState<"original" | "boxes" | "confidence">("boxes");

  if (!selectedFile) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 text-center space-y-4 bg-background">
        <FileText className="w-12 h-12 text-muted-foreground opacity-40" />
        <h3 className="text-base font-semibold text-foreground">No Document Selected</h3>
        <p className="text-xs text-muted-foreground">Select a document from the Document Manager to view its pages.</p>
        <Button variant="gradient" size="sm" onClick={() => setActiveTab("table")}>
          Go to Document Manager
        </Button>
      </div>
    );
  }

  const pageList = pages[selectedFile.id] || [];
  const currentPage = activePage || pageList[0];

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-background">
      {/* Inspector Toolbar */}
      <div className="h-12 border-b border-border/80 px-4 glass flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => setActiveTab("table")} leftIcon={<ChevronLeft className="w-4 h-4" />}>
            Back
          </Button>
          <div className="h-4 w-px bg-border" />
          <span className="text-xs font-semibold text-foreground truncate max-w-xs">{selectedFile.name}</span>
          {currentPage && (
            <Badge variant="indigo">Page {currentPage.page_number} / {selectedFile.page_count}</Badge>
          )}
        </div>

        {/* Stage Toggle */}
        <div className="flex items-center gap-1 bg-muted p-1 rounded-lg text-xs">
          <button
            onClick={() => setStage("original")}
            className={`px-2.5 py-1 rounded-md transition-colors ${stage === "original" ? "bg-card text-foreground shadow-xs font-semibold" : "text-muted-foreground"}`}
          >
            Original
          </button>
          <button
            onClick={() => setStage("boxes")}
            className={`px-2.5 py-1 rounded-md transition-colors ${stage === "boxes" ? "bg-card text-foreground shadow-xs font-semibold" : "text-muted-foreground"}`}
          >
            Bounding Boxes
          </button>
          <button
            onClick={() => setStage("confidence")}
            className={`px-2.5 py-1 rounded-md transition-colors ${stage === "confidence" ? "bg-card text-foreground shadow-xs font-semibold" : "text-muted-foreground"}`}
          >
            Confidence Heatmap
          </button>
        </div>

        {/* Zoom Controls */}
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon" onClick={() => setZoom((z) => Math.max(0.5, z - 0.25))}>
            <ZoomOut className="w-4 h-4" />
          </Button>
          <span className="text-xs font-mono-code px-2">{Math.round(zoom * 100)}%</span>
          <Button variant="ghost" size="icon" onClick={() => setZoom((z) => Math.min(2.5, z + 0.25))}>
            <ZoomIn className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {/* Main Canvas & Inspection Sidebar */}
      <div className="flex-1 flex overflow-hidden">
        {/* Canvas Area */}
        <div className="flex-1 overflow-auto p-6 flex items-center justify-center bg-slate-950/20 relative">
          {currentPage ? (
            <div
              className="relative inline-block shadow-2xl rounded border border-border/80 bg-slate-900 transition-transform duration-150"
              style={{ transform: `scale(${zoom})`, transformOrigin: "center center" }}
            >
              <img
                src={`/api/pages/${currentPage.id}/image`}
                alt={`Page ${currentPage.page_number}`}
                className="max-w-none block rounded"
              />

              {/* Overlay SVG */}
              <svg
                className="absolute inset-0 w-full h-full pointer-events-auto"
                viewBox={`0 0 ${Number.isFinite(Number(currentPage.width)) && Number(currentPage.width) > 0 ? Number(currentPage.width) : 1000} ${Number.isFinite(Number(currentPage.height)) && Number(currentPage.height) > 0 ? Number(currentPage.height) : 1000}`}
              >
                {/* Cells Overlay */}
                {stage !== "original" &&
                  currentPage.layout?.cells.map((cell: BBox, idx: number) => {
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
                          fill="rgba(99, 102, 241, 0.08)"
                          stroke="#6366f1"
                          strokeWidth={1.5}
                          strokeDasharray="4 2"
                        />
                        <text x={cx + 8} y={cy + 20} fill="#6366f1" fontSize="14" fontWeight="bold">
                          #{idx + 1}
                        </text>
                      </g>
                    );
                  })}

                {/* Lines Bounding Boxes */}
                {stage === "confidence" &&
                  currentPage.lines?.map((ln: OcrLine) => {
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
                        fill={ln.confidence >= 0.7 ? "rgba(16, 185, 129, 0.15)" : "rgba(244, 63, 94, 0.25)"}
                        stroke={ln.confidence >= 0.7 ? "#10b981" : "#f43f5e"}
                        strokeWidth={1}
                      />
                    );
                  })}
              </svg>
            </div>
          ) : (
            <div className="text-muted-foreground text-xs">Select a page to view.</div>
          )}
        </div>

        {/* Page List Sidebar */}
        <div className="w-64 border-l border-border/80 glass flex flex-col shrink-0">
          <div className="p-3 border-b border-border/60 text-xs font-semibold text-foreground flex items-center justify-between">
            <span>Pages ({pageList.length})</span>
            <Layers className="w-3.5 h-3.5 text-muted-foreground" />
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {pageList.map((p) => {
              const isSelected = currentPage?.id === p.id;
              return (
                <button
                  key={p.id}
                  onClick={() => setActivePage(p)}
                  className={`w-full flex items-center justify-between p-2 rounded-lg text-xs transition-colors text-left ${isSelected ? "bg-primary/15 text-primary font-semibold" : "hover:bg-muted text-muted-foreground"}`}
                >
                  <span>Page {p.page_number}</span>
                  <Badge variant={p.status === "completed" ? "emerald" : "slate"}>
                    {p.status}
                  </Badge>
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

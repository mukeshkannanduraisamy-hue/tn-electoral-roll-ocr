import React, { useState } from "react";
import { useOcrStore } from "@/store/useOcrStore";
import { SourceFile } from "@ocr/shared-types";
import {
  FileText,
  Upload,
  FileSpreadsheet,
  Download,
  Trash2,
  Search,
  CheckCircle2,
  Clock,
  AlertTriangle,
  ArrowUpDown,
  MoreVertical,
  Play,
  Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Input } from "@/components/ui/Input";
import { Card } from "@/components/ui/Card";
import { UploadModal } from "@/components/UploadModal";
import { BulkExtractModal } from "@/components/BulkExtractModal";
import { ExportModal } from "@/components/ExportModal";

export function DocumentView() {
  const { files, setSelectedFile, setActiveTab, deleteFile } = useOcrStore();
  const [search, setSearch] = useState("");
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [isBulkOpen, setIsBulkOpen] = useState(false);
  const [isExportOpen, setIsExportOpen] = useState(false);

  const filteredFiles = files.filter((f) =>
    f.name.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6 bg-background animate-fade-slide">
      {/* Top Header & Actions */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground flex items-center gap-2">
            <FileText className="w-6 h-6 text-primary" />
            <span>Document Manager</span>
          </h1>
          <p className="text-xs text-muted-foreground">
            Manage electoral roll PDF documents, view pipeline status, and launch OCR extractions.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="gradient"
            size="md"
            onClick={() => setIsUploadOpen(true)}
            leftIcon={<Upload className="w-4 h-4" />}
          >
            Upload PDF
          </Button>
          <Button
            variant="secondary"
            size="md"
            onClick={() => setIsBulkOpen(true)}
            leftIcon={<FileSpreadsheet className="w-4 h-4 text-violet-500" />}
          >
            Batch Extraction
          </Button>
          <Button
            variant="outline"
            size="md"
            onClick={() => setIsExportOpen(true)}
            leftIcon={<Download className="w-4 h-4 text-emerald-500" />}
          >
            Export All
          </Button>
        </div>
      </div>

      {/* Filter & Search Toolbar */}
      <Card className="p-4 flex items-center justify-between gap-4">
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Filter documents by filename..."
          leftIcon={<Search className="w-4 h-4" />}
          className="max-w-md"
        />
        <div className="text-xs text-muted-foreground font-medium">
          Showing <span className="text-foreground font-semibold">{filteredFiles.length}</span> of {files.length} documents
        </div>
      </Card>

      {/* Document Grid / Table */}
      <Card className="overflow-hidden">
        {filteredFiles.length === 0 ? (
          <div className="p-12 text-center space-y-4">
            <FileText className="w-12 h-12 text-muted-foreground mx-auto opacity-40" />
            <div className="space-y-1">
              <h3 className="text-base font-semibold text-foreground">No documents found</h3>
              <p className="text-xs text-muted-foreground">
                Upload a Tamil Nadu electoral roll PDF to start OCR extraction.
              </p>
            </div>
            <Button variant="gradient" size="sm" onClick={() => setIsUploadOpen(true)}>
              Upload First Document
            </Button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="vimc-table">
              <thead>
                <tr>
                  <th>Document Name</th>
                  <th>Pipeline Status</th>
                  <th>Pages Processed</th>
                  <th>Created Date</th>
                  <th className="text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredFiles.map((file) => (
                  <tr
                    key={file.id}
                    onClick={() => {
                      setSelectedFile(file);
                      setActiveTab("page");
                    }}
                  >
                    <td className="font-medium text-foreground">
                      <div className="flex items-center gap-3">
                        <div className="p-2 rounded-lg bg-primary/10 text-primary">
                          <FileText className="w-4 h-4" />
                        </div>
                        <div>
                          <div className="font-semibold max-w-sm truncate">{file.name}</div>
                          <div className="text-[11px] text-muted-foreground font-mono-code">{file.id}</div>
                        </div>
                      </div>
                    </td>
                    <td>
                      <Badge
                        variant={
                          file.status === "completed"
                            ? "emerald"
                            : file.status === "processing"
                            ? "indigo"
                            : file.status === "pending"
                            ? "amber"
                            : "slate"
                        }
                      >
                        {file.status}
                      </Badge>
                    </td>
                    <td>
                      <div className="flex items-center gap-2">
                        <div className="w-24 bg-muted rounded-full h-1.5 overflow-hidden">
                          <div
                            className="bg-primary h-full rounded-full transition-all"
                            style={{
                              width: `${(file.pages_done / (file.page_count || 1)) * 100}%`,
                            }}
                          />
                        </div>
                        <span className="text-xs font-mono-code">
                          {file.pages_done} / {file.page_count}
                        </span>
                      </div>
                    </td>
                    <td className="text-muted-foreground text-xs">
                      {new Date(file.created_at).toLocaleString()}
                    </td>
                    <td className="text-right" onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            setSelectedFile(file);
                            setActiveTab("page");
                          }}
                        >
                          Inspect
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="text-muted-foreground hover:text-destructive"
                          onClick={() => deleteFile(file.id)}
                          title="Delete Document"
                        >
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Modals */}
      <UploadModal isOpen={isUploadOpen} onClose={() => setIsUploadOpen(false)} />
      <BulkExtractModal isOpen={isBulkOpen} onClose={() => setIsBulkOpen(false)} />
      <ExportModal isOpen={isExportOpen} onClose={() => setIsExportOpen(false)} />
    </div>
  );
}

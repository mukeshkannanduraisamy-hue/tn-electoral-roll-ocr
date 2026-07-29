import React, { useState, useMemo } from "react";
import { useOcrStore } from "@/store/useOcrStore";
import { Voter } from "@ocr/shared-types";
import {
  Users,
  Search,
  Filter,
  Download,
  Eye,
  Building2,
  ChevronLeft,
  ChevronRight,
  ArrowUpDown,
  Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { AiFilterBar, ParsedFilter } from "@/components/AiFilterBar";
import { VoterProfilePage } from "@/components/VoterProfilePage";
import { ExportModal } from "@/components/ExportModal";

export function VotersView() {
  const { voters, setSelectedVoter, selectedVoter } = useOcrStore();
  const [activeFilter, setActiveFilter] = useState<ParsedFilter | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(25);
  const [isExportOpen, setIsExportOpen] = useState(false);
  const [sortField, setSortField] = useState<"name" | "age" | "epic_id">("name");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("asc");

  // Apply natural language AI filter rules
  const filteredVoters = useMemo(() => {
    let result = [...voters];
    if (!activeFilter) return result;

    if (activeFilter.gender) {
      result = result.filter((v) => v.gender === activeFilter.gender);
    }
    if (activeFilter.minAge !== undefined) {
      result = result.filter((v) => v.age != null && v.age >= activeFilter.minAge!);
    }
    if (activeFilter.maxAge !== undefined) {
      result = result.filter((v) => v.age != null && v.age <= activeFilter.maxAge!);
    }
    if (activeFilter.epicPrefix) {
      result = result.filter((v) => (v.epic || (v as any).epic_id || "").toUpperCase().startsWith(activeFilter.epicPrefix!));
    }
    if (activeFilter.missingHouseNumber) {
      result = result.filter((v) => !v.house_number || v.house_number === "-" || v.house_number === "");
    }
    if (activeFilter.searchTerm) {
      const term = activeFilter.searchTerm.toLowerCase();
      result = result.filter(
        (v) =>
          (v.name && v.name.toLowerCase().includes(term)) ||
          (v.epic || (v as any).epic_id || "").toLowerCase().includes(term) ||
          (v.relation_name && v.relation_name.toLowerCase().includes(term)) ||
          (v.house_number && v.house_number.toLowerCase().includes(term))
      );
    }

    // Sort
    result.sort((a, b) => {
      let valA: any = sortField === "epic_id" ? (a.epic || (a as any).epic_id) : (a as any)[sortField] || "";
      let valB: any = sortField === "epic_id" ? (b.epic || (b as any).epic_id) : (b as any)[sortField] || "";
      if (typeof valA === "string") valA = valA.toLowerCase();
      if (typeof valB === "string") valB = valB.toLowerCase();

      if (valA < valB) return sortOrder === "asc" ? -1 : 1;
      if (valA > valB) return sortOrder === "asc" ? 1 : -1;
      return 0;
    });

    return result;
  }, [voters, activeFilter, sortField, sortOrder]);

  const totalPages = Math.ceil(filteredVoters.length / pageSize) || 1;
  const paginatedVoters = filteredVoters.slice((page - 1) * pageSize, page * pageSize);

  const toggleSort = (field: "name" | "age" | "epic_id") => {
    if (sortField === field) {
      setSortOrder(sortOrder === "asc" ? "desc" : "asc");
    } else {
      setSortField(field);
      setSortOrder("asc");
    }
  };

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-background animate-fade-slide">
      {/* Top Header */}
      <div className="p-6 border-b border-border/80 flex items-center justify-between shrink-0 glass">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground flex items-center gap-2">
            <Users className="w-6 h-6 text-blue-500" />
            <span>Voter Directory & CRM</span>
          </h1>
          <p className="text-xs text-muted-foreground">
            Search, filter, and inspect verified electoral roll voter records.
          </p>
        </div>

        <Button
          variant="outline"
          size="md"
          onClick={() => setIsExportOpen(true)}
          leftIcon={<Download className="w-4 h-4 text-emerald-500" />}
        >
          Export Voters ({filteredVoters.length})
        </Button>
      </div>

      {/* Main Multi-Panel Workspace */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left/Center Panel: Data Grid & AI Search */}
        <div className="flex-1 flex flex-col p-6 space-y-4 overflow-y-auto">
          {/* AI Search Filter Bar */}
          <AiFilterBar
            onApplyQuery={(query, parsed) => {
              setActiveFilter(parsed);
              setPage(1);
            }}
            onClear={() => {
              setActiveFilter(null);
              setPage(1);
            }}
          />

          {/* Data Grid Table */}
          <Card className="overflow-hidden flex-1 flex flex-col">
            <div className="overflow-x-auto flex-1">
              <table className="vimc-table">
                <thead>
                  <tr>
                    <th onClick={() => toggleSort("epic_id")} className="cursor-pointer">
                      <div className="flex items-center gap-1">
                        <span>EPIC ID</span>
                        <ArrowUpDown className="w-3 h-3 opacity-60" />
                      </div>
                    </th>
                    <th onClick={() => toggleSort("name")} className="cursor-pointer">
                      <div className="flex items-center gap-1">
                        <span>Voter Name</span>
                        <ArrowUpDown className="w-3 h-3 opacity-60" />
                      </div>
                    </th>
                    <th>Guardian / Relative</th>
                    <th onClick={() => toggleSort("age")} className="cursor-pointer">
                      <div className="flex items-center gap-1">
                        <span>Age & Gender</span>
                        <ArrowUpDown className="w-3 h-3 opacity-60" />
                      </div>
                    </th>
                    <th>House No.</th>
                    <th className="text-right">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {paginatedVoters.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="p-8 text-center text-xs text-muted-foreground">
                        No voters match your search or filter criteria.
                      </td>
                    </tr>
                  ) : (
                    paginatedVoters.map((v) => {
                      const isSelected = selectedVoter?.id === v.id;
                      return (
                        <tr
                          key={v.id}
                          onClick={() => setSelectedVoter(v)}
                          className={isSelected ? "bg-primary/10 font-semibold" : undefined}
                        >
                          <td>
                            <span className="epic-chip">{v.epic || (v as any).epic_id || ""}</span>
                          </td>
                          <td className="font-semibold text-foreground">{v.name}</td>
                          <td className="text-muted-foreground">{v.relation_name || (v as any).guardian_name || "-"}</td>
                          <td>
                            <div className="flex items-center gap-2">
                              <Badge variant={String(v.gender).startsWith("M") ? "indigo" : "rose"}>
                                {v.gender}
                              </Badge>
                              <span className="text-xs text-muted-foreground">{v.age} yrs</span>
                            </div>
                          </td>
                          <td className="text-muted-foreground font-mono-code">{v.house_number || "-"}</td>
                          <td className="text-right">
                            <Button variant="ghost" size="sm" onClick={() => setSelectedVoter(v)}>
                              Inspect
                            </Button>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>

            {/* Pagination Controls */}
            <div className="p-3 border-t border-border/60 bg-muted/30 flex items-center justify-between text-xs text-muted-foreground">
              <span>
                Showing {Math.min((page - 1) * pageSize + 1, filteredVoters.length)} - {Math.min(page * pageSize, filteredVoters.length)} of {filteredVoters.length} voters
              </span>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page === 1}
                  onClick={() => setPage((p) => p - 1)}
                  leftIcon={<ChevronLeft className="w-3.5 h-3.5" />}
                >
                  Prev
                </Button>
                <span className="font-mono-code">Page {page} of {totalPages}</span>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => p + 1)}
                  rightIcon={<ChevronRight className="w-3.5 h-3.5" />}
                >
                  Next
                </Button>
              </div>
            </div>
          </Card>
        </div>

        {/* Right Panel: Voter CRM Profile Page */}
        {selectedVoter && (
          <div className="w-full lg:w-[580px] xl:w-[640px] border-l border-border/80 glass overflow-y-auto shrink-0 animate-slide-right">
            <VoterProfilePage />
          </div>
        )}
      </div>

      <ExportModal isOpen={isExportOpen} onClose={() => setIsExportOpen(false)} />
    </div>
  );
}

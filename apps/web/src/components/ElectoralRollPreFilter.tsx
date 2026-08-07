"use client";

import React, { useState, useEffect } from "react";
import {
  Search,
  CheckSquare,
  Square,
  ShieldCheck,
  CheckCircle2,
  Sparkles,
  Building2,
  Loader2,
  Users,
  ChevronRight,
  Database,
  Layers,
} from "lucide-react";
import { toast } from "sonner";
import { fetchExtractedOptions, ExtractedOptionPart } from "@/lib/voterApi";

export interface FilterSelection {
  constituency: string;
  selectedParts: string[];
  selectedPartName?: string;
}

interface ElectoralRollPreFilterProps {
  onApplyFilters: (selection: FilterSelection) => void;
  initialSelection?: Partial<FilterSelection>;
}

export const ElectoralRollPreFilter: React.FC<ElectoralRollPreFilterProps> = ({
  onApplyFilters,
  initialSelection,
}) => {
  const [loading, setLoading] = useState(true);
  const [districts, setDistricts] = useState<string[]>(["தர்மபுரி (Dharmapuri)"]);
  const [selectedDistrict, setSelectedDistrict] = useState<string>("தர்மபுரி (Dharmapuri)");
  const [constituencies, setConstituencies] = useState<string[]>([]);
  const [partsByAc, setPartsByAc] = useState<Record<string, ExtractedOptionPart[]>>({});
  
  const [selectedAc, setSelectedAc] = useState(initialSelection?.constituency || "");
  const [partSearch, setPartSearch] = useState("");
  const [selectedParts, setSelectedParts] = useState<string[]>(initialSelection?.selectedParts || []);

  // Fetch DB Extracted Options on Mount
  useEffect(() => {
    let isMounted = true;
    setLoading(true);
    fetchExtractedOptions()
      .then((res) => {
        if (!isMounted) return;
        if (res.districts && res.districts.length > 0) {
          setDistricts(res.districts);
          setSelectedDistrict(res.districts[0]);
        }
        const acList = res.constituencies || [];
        
        setConstituencies(acList);
        setPartsByAc(res.parts_by_ac || {});

        const initialAc = acList.find((ac) => ac === initialSelection?.constituency) || acList[0];
        setSelectedAc(initialAc);
      })
      .catch((err) => {
        console.error("Failed to fetch extracted options:", err);
        setConstituencies([]);
        setPartsByAc({});
        setSelectedAc("");
      })
      .finally(() => {
        if (isMounted) setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Available parts for selected AC
  const partsList: ExtractedOptionPart[] = partsByAc[selectedAc] || [];

  // Filter Parts by search bar
  const filteredParts = partsList.filter((p) =>
    p.name.toLowerCase().includes(partSearch.toLowerCase()) ||
    p.part_number.includes(partSearch) ||
    p.location.toLowerCase().includes(partSearch.toLowerCase())
  );

  // Click on a specific Part row -> Directly load Voter Directory for that Part
  const handlePartClick = (part: ExtractedOptionPart) => {
    const payload: FilterSelection = {
      constituency: selectedAc,
      selectedParts: [part.part_number],
      selectedPartName: part.name,
    };

    toast.success(`Loading Voter Directory for Part ${part.part_number}`, {
      description: `${part.name} (${part.voter_count.toLocaleString()} Extracted Voters)`,
    });

    onApplyFilters(payload);
  };

  // Submit all selected parts
  const handleApplyAllSelected = () => {
    const partsToLoad = selectedParts.length > 0 ? selectedParts : partsList.map((p) => p.part_number);
    const payload: FilterSelection = {
      constituency: selectedAc,
      selectedParts: partsToLoad,
    };

    toast.success(`Loaded Voter Directory for ${selectedAc}`, {
      description: `${partsToLoad.length} Polling Parts Selected`,
    });

    onApplyFilters(payload);
  };

  return (
    <div className="w-full max-w-6xl mx-auto p-4 md:p-6 space-y-6">
      {/* Header Banner */}
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-r from-slate-900 via-indigo-950 to-blue-950 text-white p-6 md:p-8 shadow-xl border border-white/10">
        <div className="absolute -right-10 -bottom-10 w-64 h-64 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none" />
        <div className="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1.5">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-500/20 text-indigo-300 text-xs font-semibold backdrop-blur-sm border border-indigo-400/20">
              <Database className="w-3.5 h-3.5 text-indigo-400" />
              <span>Extracted Database Polling Parts</span>
            </div>
            <h1 className="text-2xl md:text-3xl font-extrabold tracking-tight bg-gradient-to-r from-white via-slate-100 to-indigo-200 bg-clip-text text-transparent">
              Select Polling Part for Voter Directory
            </h1>
            <p className="text-sm text-slate-300 max-w-2xl">
              Choose District & Assembly Constituency, then click any Part No & Part Name to view its complete voter list. Only extracted database options are shown.
            </p>
          </div>
        </div>
      </div>

      {/* Filter Options: District, Assembly Constituency *, Part Search */}
      <div className="bg-card text-card-foreground rounded-2xl border border-border/60 shadow-lg p-6 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* 1. District Filter */}
          <div className="space-y-1.5">
            <label className="text-xs font-bold text-foreground/80 flex items-center gap-1.5">
              <Building2 className="w-4 h-4 text-indigo-500" />
              District
            </label>
            <select
              value={selectedDistrict}
              onChange={(e) => setSelectedDistrict(e.target.value)}
              className="w-full h-10 px-3 rounded-lg border border-input bg-background text-sm font-semibold focus:ring-2 focus:ring-primary focus:outline-none transition-colors"
            >
              {districts.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </div>

          {/* 2. Assembly Constituency * Filter */}
          <div className="space-y-1.5">
            <label className="text-xs font-bold text-foreground/80 flex items-center gap-1.5">
              <Building2 className="w-4 h-4 text-indigo-500" />
              Assembly Constituency <span className="text-rose-500 font-bold">*</span>
            </label>

            {loading ? (
              <div className="h-10 px-3 rounded-lg border border-input bg-muted/50 flex items-center text-xs text-muted-foreground gap-2">
                <Loader2 className="w-4 h-4 animate-spin text-primary" />
                <span>Loading DB constituencies...</span>
              </div>
            ) : (
              <select
                value={selectedAc}
                onChange={(e) => {
                  setSelectedAc(e.target.value);
                  setSelectedParts([]);
                }}
                className="w-full h-10 px-3 rounded-lg border border-input bg-background text-sm font-semibold focus:ring-2 focus:ring-primary focus:outline-none transition-colors"
              >
                {constituencies.map((ac) => (
                  <option key={ac} value={ac}>
                    {ac}
                  </option>
                ))}
              </select>
            )}
          </div>

          {/* 3. Part No and Part Name Search */}
          <div className="space-y-1.5">
            <label className="text-xs font-bold text-foreground/80 flex items-center gap-1.5">
              <Search className="w-4 h-4 text-indigo-500" />
              Search Part No or Part Name
            </label>
            <div className="relative">
              <input
                type="text"
                placeholder="Type part number or location name..."
                value={partSearch}
                onChange={(e) => setPartSearch(e.target.value)}
                className="w-full h-10 pl-9 pr-4 rounded-lg border border-input bg-background text-sm focus:ring-2 focus:ring-primary focus:outline-none transition-colors"
              />
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            </div>
          </div>
        </div>
      </div>

      {/* Extracted Part No and Part Name Table */}
      <div className="bg-card text-card-foreground rounded-2xl border border-border/60 shadow-md overflow-hidden">
        {/* Table Header */}
        <div className="bg-gradient-to-r from-indigo-950 via-slate-900 to-blue-950 text-white p-4 flex items-center justify-between border-b border-white/10">
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-indigo-400" />
            <span className="text-xs font-bold uppercase tracking-wider text-slate-200">
              Part No and Part Name ({selectedAc || "Database Parts"})
            </span>
          </div>

          <span className="text-xs text-indigo-300 font-medium">
            Click any row to view its Voter List
          </span>
        </div>

        {/* Table Body */}
        <div className="divide-y divide-border/40 max-h-[500px] overflow-y-auto">
          {loading ? (
            <div className="p-12 text-center text-muted-foreground space-y-3">
              <Loader2 className="w-8 h-8 mx-auto animate-spin text-primary" />
              <p className="text-sm font-medium">Loading extracted polling parts from database...</p>
            </div>
          ) : filteredParts.length === 0 ? (
            <div className="p-12 text-center text-muted-foreground space-y-2">
              <Search className="w-8 h-8 mx-auto text-muted-foreground/40 animate-bounce" />
              <p className="text-sm font-semibold">No extracted parts found matching "{partSearch}"</p>
              <p className="text-xs text-muted-foreground">Upload and process a PDF roll to extract voter records into DB.</p>
            </div>
          ) : (
            filteredParts.map((part) => (
              <div
                key={part.part_number}
                onClick={() => handlePartClick(part)}
                className="p-4.5 flex items-center justify-between gap-4 hover:bg-indigo-50/80 dark:hover:bg-indigo-950/50 transition-all cursor-pointer group select-none"
              >
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 rounded-xl bg-indigo-500/10 dark:bg-indigo-500/20 text-indigo-600 dark:text-indigo-400 flex items-center justify-center font-bold text-sm shrink-0 group-hover:scale-105 transition-transform">
                    {part.part_number}
                  </div>

                  <div className="space-y-1">
                    <div className="text-sm font-bold text-foreground group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors">
                      {part.name}
                    </div>
                    <div className="text-xs text-muted-foreground flex items-center gap-3">
                      <span>Location: {part.location}</span>
                      <span>PIN: {part.pin}</span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-3 shrink-0">
                  <div className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 text-xs font-bold">
                    <Users className="w-3.5 h-3.5" />
                    <span>{part.voter_count.toLocaleString()} Extracted Voters</span>
                  </div>

                  <div className="w-8 h-8 rounded-full bg-muted group-hover:bg-indigo-600 group-hover:text-white text-muted-foreground flex items-center justify-center transition-all">
                    <ChevronRight className="w-4 h-4" />
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};

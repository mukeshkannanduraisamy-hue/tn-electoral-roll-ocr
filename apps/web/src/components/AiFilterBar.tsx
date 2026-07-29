import React, { useState } from "react";
import { Sparkles, Search, X, Filter, SlidersHorizontal } from "lucide-react";
import { cn } from "@/lib/utils";

interface AiFilterBarProps {
  onApplyQuery: (query: string, parsedFilters: ParsedFilter) => void;
  onClear: () => void;
  className?: string;
}

export interface ParsedFilter {
  gender?: string;
  minAge?: number;
  maxAge?: number;
  epicPrefix?: string;
  pollingStationId?: string;
  lowConfidence?: boolean;
  missingHouseNumber?: boolean;
  duplicateOnly?: boolean;
  searchTerm?: string;
}

export function parseNaturalLanguageQuery(query: string): ParsedFilter {
  const q = query.toLowerCase().trim();
  const filter: ParsedFilter = {};

  if (!q) return filter;

  // Gender
  if (q.includes("male") && !q.includes("female")) filter.gender = "M";
  if (q.includes("female")) filter.gender = "F";

  // Age rules
  const aboveMatch = q.match(/(?:above|older than|>)\s*(\d+)/);
  if (aboveMatch) filter.minAge = parseInt(aboveMatch[1], 10);

  const belowMatch = q.match(/(?:below|younger than|<)\s*(\d+)/);
  if (belowMatch) filter.maxAge = parseInt(belowMatch[1], 10);

  const rangeMatch = q.match(/(?:between|age)\s*(\d+)\s*(?:and|-|to)\s*(\d+)/);
  if (rangeMatch) {
    filter.minAge = parseInt(rangeMatch[1], 10);
    filter.maxAge = parseInt(rangeMatch[2], 10);
  }

  // Low confidence / OCR rules
  if (q.includes("confidence") || q.includes("ocr error") || q.includes("review")) {
    filter.lowConfidence = true;
  }

  // Missing house number
  if (q.includes("missing house") || q.includes("no house") || q.includes("no address")) {
    filter.missingHouseNumber = true;
  }

  // Duplicate
  if (q.includes("duplicate") || q.includes("dup")) {
    filter.duplicateOnly = true;
  }

  // EPIC prefix
  const epicMatch = q.match(/\b([a-z]{2,4}\d*)\b/);
  if (epicMatch && (q.includes("epic") || q.includes("starts with") || q.includes("tn"))) {
    filter.epicPrefix = epicMatch[1].toUpperCase();
  }

  // Polling Station
  const stationMatch = q.match(/(?:station|booth|ps)\s*#?\s*(\d+)/);
  if (stationMatch) {
    filter.pollingStationId = stationMatch[1];
  }

  filter.searchTerm = q;
  return filter;
}

export function AiFilterBar({ onApplyQuery, onClear, className }: AiFilterBarProps) {
  const [query, setQuery] = useState("");
  const [activeFilter, setActiveFilter] = useState<ParsedFilter | null>(null);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) {
      setActiveFilter(null);
      onClear();
      return;
    }
    const parsed = parseNaturalLanguageQuery(query);
    setActiveFilter(parsed);
    onApplyQuery(query, parsed);
  };

  const handleClear = () => {
    setQuery("");
    setActiveFilter(null);
    onClear();
  };

  const quickPresets = [
    "Male voters above 60",
    "Female voters under 30",
    "Missing house number",
    "Low OCR confidence",
    "EPIC starts with TN",
  ];

  return (
    <div className={cn("flex flex-col gap-2 w-full", className)}>
      <form onSubmit={handleSearch} className="relative flex items-center w-full">
        <div className="absolute left-3 flex items-center text-indigo-500 pointer-events-none">
          <Sparkles className="w-4 h-4 animate-pulse" />
        </div>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Ask AI or search: e.g. 'Male voters above 60', 'EPIC starts with TN', 'Missing house number'..."
          className="w-full h-10 pl-9 pr-24 rounded-lg border border-indigo-500/30 bg-indigo-500/5 dark:bg-indigo-950/20 text-sm font-medium focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 transition-all placeholder:text-muted-foreground/80"
        />
        <div className="absolute right-2 flex items-center gap-1.5">
          {query && (
            <button
              type="button"
              onClick={handleClear}
              className="p-1 rounded text-muted-foreground hover:text-foreground"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
          <button
            type="submit"
            className="px-2.5 py-1 text-xs font-semibold rounded-md bg-indigo-600 hover:bg-indigo-500 text-white shadow-xs transition-colors flex items-center gap-1"
          >
            <Search className="w-3 h-3" />
            <span>Search</span>
          </button>
        </div>
      </form>

      {/* Preset Suggestions */}
      <div className="flex items-center gap-1.5 overflow-x-auto pb-1 text-xs text-muted-foreground">
        <span className="text-[11px] font-medium shrink-0 flex items-center gap-1 text-indigo-500">
          <SlidersHorizontal className="w-3 h-3" /> Presets:
        </span>
        {quickPresets.map((preset) => (
          <button
            key={preset}
            type="button"
            onClick={() => {
              setQuery(preset);
              const parsed = parseNaturalLanguageQuery(preset);
              setActiveFilter(parsed);
              onApplyQuery(preset, parsed);
            }}
            className="px-2 py-0.5 rounded-full bg-muted/60 hover:bg-indigo-500/10 hover:text-indigo-500 border border-border/50 transition-colors whitespace-nowrap text-[11px]"
          >
            {preset}
          </button>
        ))}
      </div>

      {/* Active Filter Chips */}
      {activeFilter && (
        <div className="flex items-center gap-2 flex-wrap pt-1 text-xs">
          <span className="text-[11px] text-muted-foreground">Parsed Filters:</span>
          {activeFilter.gender && (
            <span className="badge-indigo text-[11px]">Gender: {activeFilter.gender}</span>
          )}
          {activeFilter.minAge && (
            <span className="badge-sky text-[11px]">Min Age: {activeFilter.minAge}</span>
          )}
          {activeFilter.maxAge && (
            <span className="badge-sky text-[11px]">Max Age: {activeFilter.maxAge}</span>
          )}
          {activeFilter.epicPrefix && (
            <span className="badge-slate text-[11px]">EPIC: {activeFilter.epicPrefix}*</span>
          )}
          {activeFilter.pollingStationId && (
            <span className="badge-amber text-[11px]">Station #{activeFilter.pollingStationId}</span>
          )}
          {activeFilter.lowConfidence && (
            <span className="badge-rose text-[11px]">Low Confidence</span>
          )}
          {activeFilter.missingHouseNumber && (
            <span className="badge-rose text-[11px]">Missing House No.</span>
          )}
        </div>
      )}
    </div>
  );
}

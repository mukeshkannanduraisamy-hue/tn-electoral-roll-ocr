"use client";

import React, { useEffect, useState } from "react";
import {
  Building2,
  MapPin,
  Users,
  Search,
  RefreshCw,
  Loader2,
  ChevronRight,
  Map,
  Camera,
  Image as ImageIcon,
  CheckCircle2,
} from "lucide-react";
import { toast } from "sonner";

interface PollingStation {
  id: string;
  part_number: string;
  name: string;
  name_tam: string;
  building_name: string;
  section_details: string;
  total_electors: number;
  male_electors: number;
  female_electors: number;
  third_gender_electors: number;
  voter_count: number;
  photo_count: number;
  photos: Array<{ id: string; photo_type: string; file_path: string }>;
}

export const PollingStationsView: React.FC = () => {
  const [stations, setStations] = useState<PollingStation[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [selectedStation, setSelectedStation] = useState<PollingStation | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/polling-stations?search=${encodeURIComponent(search)}`, {
        credentials: "same-origin",
      });
      if (res.ok) {
        const data = await res.json();
        setStations(data.items || []);
      }
    } catch {
      toast.error("Failed to load polling stations");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, [search]);

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-background">
      {/* Header */}
      <div className="shrink-0 px-6 py-4 border-b border-border bg-card/60 backdrop-blur-sm">
        <div className="flex items-center justify-between gap-4 mb-3">
          <div>
            <h1 className="text-lg font-bold text-foreground">Polling Stations Intelligence</h1>
            <p className="text-xs text-muted-foreground">
              {stations.length} Polling Stations & Map Assets Registered
            </p>
          </div>
          <button onClick={() => void load()} className="vims-btn-ghost h-8 w-8 p-0 justify-center">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>

        {/* Search */}
        <div className="relative max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground pointer-events-none" />
          <input
            type="text"
            placeholder="Search part number, station name, building…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="vims-input pl-9 h-8 text-xs"
          />
        </div>
      </div>

      {/* Grid Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {loading ? (
          <div className="flex items-center justify-center h-64">
            <Loader2 className="w-6 h-6 animate-spin text-primary" />
          </div>
        ) : stations.length === 0 ? (
          <div className="text-center py-16">
            <Building2 className="w-12 h-12 mx-auto mb-3 text-muted-foreground/30" />
            <p className="text-sm font-semibold text-foreground">No Polling Stations Found</p>
            <p className="text-xs text-muted-foreground mt-1">Import Electoral Roll PDFs to populate polling station intelligence.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {stations.map((st) => (
              <div key={st.id} className="card-vims p-5 space-y-4 hover:border-primary/40 transition-all">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-white font-bold text-sm">
                      P{st.part_number}
                    </div>
                    <div>
                      <h3 className="text-sm font-bold text-foreground leading-tight">{st.name}</h3>
                      <p className="text-xs text-muted-foreground mt-0.5">Part No. {st.part_number}</p>
                    </div>
                  </div>
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded-full badge-blue">
                    {st.voter_count} Voters
                  </span>
                </div>

                {st.building_name && (
                  <div className="flex items-start gap-2 text-xs text-muted-foreground">
                    <Building2 className="w-3.5 h-3.5 shrink-0 mt-0.5 text-primary" />
                    <span className="line-clamp-2">{st.building_name}</span>
                  </div>
                )}

                {/* Map & Photo Tags */}
                <div className="grid grid-cols-2 gap-2 pt-2 border-t border-border">
                  <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                    <Map className="w-3 h-3 text-indigo-400" />
                    <span>Nazri Naksha</span>
                  </div>
                  <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                    <Camera className="w-3 h-3 text-teal-400" />
                    <span>Building Front</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

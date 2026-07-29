import React, { useState } from "react";
import { useOcrStore } from "@/store/useOcrStore";
import { Building2, MapPin, Users, PieChart, Search, CheckCircle2, ChevronRight } from "lucide-react";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";

export function PollingStationsView() {
  const { pollingStations, voters, setActiveTab } = useOcrStore();
  const [search, setSearch] = useState("");

  const filteredStations = pollingStations.filter(
    (ps) =>
      ps.name.toLowerCase().includes(search.toLowerCase()) ||
      ps.station_number.toString().includes(search)
  );

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6 bg-background animate-fade-slide">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground flex items-center gap-2">
            <Building2 className="w-6 h-6 text-teal-500" />
            <span>Polling Station Intelligence</span>
          </h1>
          <p className="text-xs text-muted-foreground">
            Booth-level demographic analytics, voter roll completeness, and station metrics.
          </p>
        </div>

        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search stations by name or number..."
          leftIcon={<Search className="w-4 h-4" />}
          className="max-w-xs"
        />
      </div>

      {/* Grid of Polling Stations */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filteredStations.length === 0 ? (
          <Card className="col-span-full p-8 text-center text-xs text-muted-foreground">
            No polling stations found. Process electoral roll documents to extract booth data.
          </Card>
        ) : (
          filteredStations.map((station) => {
            const stationVoters = voters.filter(
              (v) => v.polling_station_id === station.id
            );
            const maleCount = stationVoters.filter((v) => String(v.gender).startsWith("M")).length;
            const femaleCount = stationVoters.filter((v) => String(v.gender).startsWith("F")).length;

            return (
              <Card key={station.id} className="p-5 space-y-4 hover:border-teal-500/30 transition-all">
                <div className="flex items-start justify-between">
                  <div className="space-y-1">
                    <Badge variant="sky">Booth #{station.station_number}</Badge>
                    <h3 className="text-base font-bold text-foreground line-clamp-1">{station.name}</h3>
                  </div>
                  <div className="p-2 rounded-xl bg-teal-500/10 text-teal-500">
                    <Building2 className="w-5 h-5" />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div className="p-2.5 rounded-lg bg-muted/50 border border-border/40">
                    <span className="text-muted-foreground block text-[10px]">Voters Count</span>
                    <span className="text-lg font-bold text-foreground font-mono-code">{stationVoters.length || station.voter_count || 0}</span>
                  </div>
                  <div className="p-2.5 rounded-lg bg-muted/50 border border-border/40">
                    <span className="text-muted-foreground block text-[10px]">Gender Ratio</span>
                    <span className="text-xs font-semibold text-foreground">{maleCount} M / {femaleCount} F</span>
                  </div>
                </div>

                <div className="pt-2 border-t border-border/60 flex items-center justify-between">
                  <span className="text-xs text-muted-foreground flex items-center gap-1">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                    <span>Verified Data</span>
                  </span>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setActiveTab("voters")}
                    rightIcon={<ChevronRight className="w-3.5 h-3.5" />}
                  >
                    View Roll
                  </Button>
                </div>
              </Card>
            );
          })
        )}
      </div>
    </div>
  );
}

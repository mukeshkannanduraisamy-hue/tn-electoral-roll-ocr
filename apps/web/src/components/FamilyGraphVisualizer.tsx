import React from "react";
import { Users, Home, MapPin, Building2, ChevronRight } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";

interface FamilyMember {
  id: string;
  name: string;
  relation?: string;
  epic_id: string;
  age: number | null;
  gender: string;
}

interface FamilyGraphProps {
  houseNumber: string;
  streetName?: string;
  pollingStationName?: string;
  members: FamilyMember[];
  currentVoterId?: string;
  onSelectVoter?: (voterId: string) => void;
}

export function FamilyGraphVisualizer({
  houseNumber,
  streetName = "Main Street",
  pollingStationName = "Station #132",
  members,
  currentVoterId,
  onSelectVoter,
}: FamilyGraphProps) {
  return (
    <Card className="p-4 space-y-4 bg-muted/20 border-indigo-500/20">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Home className="w-4 h-4 text-indigo-500" />
          <h4 className="text-xs font-semibold text-foreground">Household Relationship Graph</h4>
        </div>
        <Badge variant="indigo">{members.length} Household Members</Badge>
      </div>

      {/* Visual Hierarchy Nodes */}
      <div className="space-y-3 relative pl-4 border-l-2 border-indigo-500/30">
        {/* Level 1: Polling Station */}
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Building2 className="w-3.5 h-3.5 text-teal-500 shrink-0" />
          <span className="font-semibold text-foreground">{pollingStationName}</span>
        </div>

        {/* Level 2: Street */}
        <div className="flex items-center gap-2 text-xs text-muted-foreground pl-3">
          <MapPin className="w-3.5 h-3.5 text-amber-500 shrink-0" />
          <span>{streetName}</span>
        </div>

        {/* Level 3: House Cluster */}
        <div className="pl-6 space-y-2 pt-1">
          <div className="flex items-center gap-2 text-xs font-semibold text-indigo-400">
            <Home className="w-3.5 h-3.5" />
            <span>House No. {houseNumber || "Unassigned"}</span>
          </div>

          {/* Member Node Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
            {members.map((m) => {
              const isSelected = m.id === currentVoterId;
              return (
                <div
                  key={m.id}
                  onClick={() => onSelectVoter?.(m.id)}
                  className={`p-2.5 rounded-lg border text-xs flex items-center justify-between transition-all cursor-pointer ${
                    isSelected
                      ? "bg-indigo-500/15 border-indigo-500 text-indigo-400 shadow-xs font-semibold"
                      : "bg-card hover:bg-muted border-border text-foreground"
                  }`}
                >
                  <div className="flex items-center gap-2 truncate">
                    <div className={`w-6 h-6 rounded-full flex items-center justify-center font-bold text-[10px] ${m.gender === "M" ? "bg-blue-500/20 text-blue-400" : "bg-rose-500/20 text-rose-400"}`}>
                      {m.gender}
                    </div>
                    <div className="truncate">
                      <div className="truncate font-medium">{m.name}</div>
                      <div className="text-[10px] text-muted-foreground font-mono-code">{m.epic_id}</div>
                    </div>
                  </div>
                  <span className="text-[11px] text-muted-foreground shrink-0">{m.age} yrs</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </Card>
  );
}

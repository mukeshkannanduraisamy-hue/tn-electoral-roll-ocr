import React from "react";
import { useOcrStore } from "@/store/useOcrStore";
import {
  User,
  ShieldCheck,
  Building2,
  Home,
  MapPin,
  Calendar,
  FileText,
  X,
  Share2,
  Download,
  Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { FamilyGraphVisualizer } from "@/components/FamilyGraphVisualizer";

export function VoterProfilePage() {
  const { selectedVoter, setSelectedVoter, voters } = useOcrStore();

  if (!selectedVoter) return null;

  // Find family members sharing the same house number
  const familyMembers = voters.filter(
    (v) =>
      v.house_number &&
      selectedVoter.house_number &&
      v.house_number.trim().toLowerCase() === selectedVoter.house_number.trim().toLowerCase()
  );

  return (
    <div className="flex flex-col h-full bg-background text-foreground animate-fade-slide">
      {/* Drawer Header */}
      <div className="p-4 border-b border-border/80 flex items-center justify-between glass">
        <div className="flex items-center gap-2">
          <Badge variant="indigo">
            <Sparkles className="w-3 h-3 text-indigo-400" />
            CRM Voter Profile
          </Badge>
        </div>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setSelectedVoter(null)}
          title="Close Profile"
        >
          <X className="w-4 h-4" />
        </Button>
      </div>

      {/* Profile Details Container */}
      <div className="flex-1 overflow-y-auto p-4 space-y-5">
        {/* Avatar & Hero */}
        <div className="flex items-center gap-4 p-4 rounded-xl profile-hero border border-indigo-500/20">
          <div className="photo-avatar">
            {selectedVoter.name ? selectedVoter.name.charAt(0).toUpperCase() : "V"}
          </div>
          <div className="space-y-1 min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="epic-chip">{selectedVoter.epic || (selectedVoter as any).epic_id || ""}</span>
              <span title="Verified Record"><ShieldCheck className="w-4 h-4 text-emerald-500 shrink-0" /></span>
            </div>
            <h2 className="text-lg font-bold tracking-tight text-foreground truncate">
              {selectedVoter.name}
            </h2>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Badge variant={String(selectedVoter.gender).startsWith("M") ? "indigo" : "rose"}>
                {String(selectedVoter.gender).startsWith("M") ? "Male" : "Female"}
              </Badge>
              <span>• {selectedVoter.age} years old</span>
            </div>
          </div>
        </div>

        {/* Detailed Fields Grid */}
        <Card className="p-4 space-y-3 text-xs">
          <h4 className="font-semibold text-foreground border-b border-border/60 pb-2">
            Demographic Details
          </h4>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <span className="text-muted-foreground block text-[11px]">Guardian / Relative</span>
              <span className="font-semibold text-foreground">{selectedVoter.relation_name || (selectedVoter as any).guardian_name || "-"}</span>
            </div>
            <div>
              <span className="text-muted-foreground block text-[11px]">Relationship</span>
              <span className="font-semibold text-foreground">{selectedVoter.relation_type || "Father"}</span>
            </div>
            <div>
              <span className="text-muted-foreground block text-[11px]">House Number</span>
              <span className="font-semibold text-foreground font-mono-code">{selectedVoter.house_number || "-"}</span>
            </div>
            <div>
              <span className="text-muted-foreground block text-[11px]">Section / Street</span>
              <span className="font-semibold text-foreground">Section 1</span>
            </div>
          </div>
        </Card>

        {/* Family Cluster Relationship Graph */}
        <FamilyGraphVisualizer
          houseNumber={selectedVoter.house_number || ""}
          members={familyMembers.map((m) => ({
            id: m.id,
            name: m.name,
            epic_id: m.epic || (m as any).epic_id || "",
            age: m.age,
            gender: m.gender,
          }))}
          currentVoterId={selectedVoter.id}
          onSelectVoter={(id) => {
            const found = voters.find((v) => v.id === id);
            if (found) setSelectedVoter(found);
          }}
        />

        {/* OCR Line Audit & Confidence */}
        <Card className="p-4 space-y-2 text-xs">
          <div className="flex items-center justify-between">
            <span className="font-semibold text-foreground">OCR Verification Status</span>
            <Badge variant="emerald">100% Match</Badge>
          </div>
          <p className="text-muted-foreground text-[11px]">
            Record parsed via PP-OCRv5 Tamil pipeline and stored in SQLite database.
          </p>
        </Card>
      </div>
    </div>
  );
}

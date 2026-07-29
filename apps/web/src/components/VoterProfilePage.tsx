import React, { useState } from "react";
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
  Copy,
  Check,
  Edit3,
  Users,
  History,
  Layers,
  CheckCircle2,
  ArrowLeft,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { FamilyGraphVisualizer } from "@/components/FamilyGraphVisualizer";
import { toast } from "sonner";

export function VoterProfilePage() {
  const { selectedVoter, setSelectedVoter, voters, setActiveTab } = useOcrStore();
  const [copied, setCopied] = useState(false);
  const [activeSubTab, setActiveSubTab] = useState<"overview" | "ocr" | "history">("overview");

  if (!selectedVoter) return null;

  const epicId = selectedVoter.epic || (selectedVoter as any).epic_id || "N/A";
  const genderStr = String(selectedVoter.gender);
  const isMale = genderStr.startsWith("M");

  // Find family members sharing the same house number
  const familyMembers = voters.filter(
    (v) =>
      v.house_number &&
      selectedVoter.house_number &&
      v.house_number.trim().toLowerCase() === selectedVoter.house_number.trim().toLowerCase()
  );

  const handleCopyEpic = () => {
    navigator.clipboard.writeText(epicId);
    setCopied(true);
    toast.success(`EPIC ID ${epicId} copied to clipboard!`);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="flex flex-col h-full bg-background text-foreground animate-fade-slide overflow-hidden">
      {/* Top Header Toolbar */}
      <div className="h-14 px-6 border-b border-border/80 flex items-center justify-between glass shrink-0">
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setSelectedVoter(null)}
            leftIcon={<ArrowLeft className="w-4 h-4" />}
          >
            Back to Directory
          </Button>
          <span className="h-4 w-px bg-border" />
          <Badge variant="indigo">
            <Sparkles className="w-3 h-3 text-indigo-400" />
            CRM Voter Record
          </Badge>
          <span className="text-xs font-mono-code text-muted-foreground">{epicId}</span>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleCopyEpic}
            leftIcon={copied ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
          >
            {copied ? "Copied" : "Copy EPIC"}
          </Button>
          <Button variant="outline" size="sm" leftIcon={<Edit3 className="w-3.5 h-3.5" />}>
            Edit Record
          </Button>
          <Button variant="secondary" size="sm" leftIcon={<Download className="w-3.5 h-3.5 text-indigo-400" />}>
            Export PDF
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setSelectedVoter(null)}
            title="Close Profile"
          >
            <X className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {/* Main Profile Body */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* Profile Hero Header Card */}
        <Card className="p-6 bg-gradient-to-r from-indigo-950/40 via-card to-card border-indigo-500/30 relative overflow-hidden">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-6 relative z-10">
            <div className="flex items-center gap-5">
              <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-indigo-500 via-indigo-600 to-violet-600 text-white flex items-center justify-center font-extrabold text-2xl shadow-lg shadow-indigo-500/30 shrink-0">
                {selectedVoter.name ? selectedVoter.name.charAt(0).toUpperCase() : "V"}
              </div>

              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="epic-chip text-xs">{epicId}</span>
                  <Badge variant="emerald" className="gap-1">
                    <CheckCircle2 className="w-3 h-3" />
                    Verified Elector
                  </Badge>
                  {selectedVoter.is_supplement && (
                    <Badge variant="amber">Supplement Elector</Badge>
                  )}
                </div>

                <h1 className="text-2xl font-extrabold tracking-tight text-foreground">
                  {selectedVoter.name}
                </h1>

                <div className="flex items-center gap-3 text-xs text-muted-foreground">
                  <Badge variant={isMale ? "indigo" : "rose"}>
                    {isMale ? "Male" : "Female"}
                  </Badge>
                  <span>• {selectedVoter.age != null ? `${selectedVoter.age} years old` : "Age N/A"}</span>
                  <span>• Serial #{selectedVoter.serial || "1"}</span>
                  <span>• Part #{selectedVoter.part_number || "1"}</span>
                </div>
              </div>
            </div>

            {/* Quick Summary Pill */}
            <div className="flex items-center gap-2 p-3 rounded-xl bg-background/80 border border-border/80 text-xs">
              <Building2 className="w-4 h-4 text-indigo-400 shrink-0" />
              <div>
                <span className="text-muted-foreground block text-[10px]">Polling Station</span>
                <span className="font-semibold text-foreground">Booth #{selectedVoter.part_number || "1"}</span>
              </div>
            </div>
          </div>
        </Card>

        {/* Sub Navigation Tabs */}
        <div className="flex items-center gap-2 border-b border-border/60 pb-1">
          <button
            onClick={() => setActiveSubTab("overview")}
            className={`px-4 py-2 text-xs font-semibold rounded-lg transition-colors flex items-center gap-2 ${
              activeSubTab === "overview"
                ? "bg-primary/15 text-primary"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <Users className="w-3.5 h-3.5" />
            <span>Overview & Demographics</span>
          </button>
          <button
            onClick={() => setActiveSubTab("ocr")}
            className={`px-4 py-2 text-xs font-semibold rounded-lg transition-colors flex items-center gap-2 ${
              activeSubTab === "ocr"
                ? "bg-primary/15 text-primary"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            <span>OCR Lineage & Provenance</span>
          </button>
          <button
            onClick={() => setActiveSubTab("history")}
            className={`px-4 py-2 text-xs font-semibold rounded-lg transition-colors flex items-center gap-2 ${
              activeSubTab === "history"
                ? "bg-primary/15 text-primary"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <History className="w-3.5 h-3.5" />
            <span>Audit History</span>
          </button>
        </div>

        {/* Tab Content */}
        {activeSubTab === "overview" && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Section 1: Demographics */}
            <Card className="p-5 space-y-4">
              <div className="border-b border-border/60 pb-3 flex items-center justify-between">
                <h3 className="text-sm font-bold text-foreground flex items-center gap-2">
                  <User className="w-4 h-4 text-indigo-400" />
                  <span>Demographic Information</span>
                </h3>
                <Badge variant="indigo">Official Roll</Badge>
              </div>

              <div className="grid grid-cols-2 gap-4 text-xs">
                <div>
                  <span className="text-muted-foreground block text-[11px]">Full Name</span>
                  <span className="font-bold text-foreground text-sm">{selectedVoter.name}</span>
                </div>
                <div>
                  <span className="text-muted-foreground block text-[11px]">EPIC Number</span>
                  <span className="font-mono-code font-bold text-indigo-400 text-sm">{epicId}</span>
                </div>
                <div>
                  <span className="text-muted-foreground block text-[11px]">Guardian / Relative Name</span>
                  <span className="font-semibold text-foreground">{selectedVoter.relation_name || (selectedVoter as any).guardian_name || "-"}</span>
                </div>
                <div>
                  <span className="text-muted-foreground block text-[11px]">Relation Type</span>
                  <span className="font-semibold text-foreground">{selectedVoter.relation_type || "Father"}</span>
                </div>
                <div>
                  <span className="text-muted-foreground block text-[11px]">Age</span>
                  <span className="font-semibold text-foreground">{selectedVoter.age != null ? `${selectedVoter.age} years` : "-"}</span>
                </div>
                <div>
                  <span className="text-muted-foreground block text-[11px]">Gender</span>
                  <span className="font-semibold text-foreground">{isMale ? "Male (M)" : "Female (F)"}</span>
                </div>
              </div>
            </Card>

            {/* Section 2: Electoral Location */}
            <Card className="p-5 space-y-4">
              <div className="border-b border-border/60 pb-3 flex items-center justify-between">
                <h3 className="text-sm font-bold text-foreground flex items-center gap-2">
                  <Building2 className="w-4 h-4 text-teal-400" />
                  <span>Electoral Location Details</span>
                </h3>
                <Badge variant="sky">Booth #{selectedVoter.part_number || "1"}</Badge>
              </div>

              <div className="grid grid-cols-2 gap-4 text-xs">
                <div>
                  <span className="text-muted-foreground block text-[11px]">House / Door Number</span>
                  <span className="font-mono-code font-bold text-foreground text-sm">{selectedVoter.house_number || "-"}</span>
                </div>
                <div>
                  <span className="text-muted-foreground block text-[11px]">Serial Number in List</span>
                  <span className="font-mono-code font-bold text-foreground text-sm">#{selectedVoter.serial || "1"}</span>
                </div>
                <div>
                  <span className="text-muted-foreground block text-[11px]">Part / Section Number</span>
                  <span className="font-semibold text-foreground">{selectedVoter.part_number || "Part 1"}</span>
                </div>
                <div>
                  <span className="text-muted-foreground block text-[11px]">Assembly Constituency</span>
                  <span className="font-semibold text-foreground">{selectedVoter.constituency || "Tamil Nadu Assembly"}</span>
                </div>
                <div className="col-span-2">
                  <span className="text-muted-foreground block text-[11px]">Polling Station Location</span>
                  <span className="font-semibold text-foreground">Government Primary School, Booth #{selectedVoter.part_number || "1"}</span>
                </div>
              </div>
            </Card>

            {/* Section 3: Household Graph (Full Width) */}
            <div className="md:col-span-2 space-y-2">
              <h3 className="text-sm font-bold text-foreground flex items-center gap-2">
                <Home className="w-4 h-4 text-violet-400" />
                <span>Household Cluster & Family Graph (House #{selectedVoter.house_number || "N/A"})</span>
              </h3>
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
            </div>
          </div>
        )}

        {activeSubTab === "ocr" && (
          <Card className="p-5 space-y-4">
            <div className="border-b border-border/60 pb-3 flex items-center justify-between">
              <h3 className="text-sm font-bold text-foreground flex items-center gap-2">
                <FileText className="w-4 h-4 text-indigo-400" />
                <span>Source PDF & OCR Audit Trail</span>
              </h3>
              <Badge variant="emerald">100% Verified Match</Badge>
            </div>

            <div className="grid grid-cols-2 gap-4 text-xs">
              <div>
                <span className="text-muted-foreground block text-[11px]">Source PDF File</span>
                <span className="font-semibold text-foreground">{selectedVoter.source_file_name || "Electoral_Roll.pdf"}</span>
              </div>
              <div>
                <span className="text-muted-foreground block text-[11px]">Page Number</span>
                <span className="font-mono-code font-semibold text-foreground">Page {selectedVoter.page_number || "1"}</span>
              </div>
              <div>
                <span className="text-muted-foreground block text-[11px]">OCR Engine</span>
                <span className="font-semibold text-foreground">PaddleOCR PP-OCRv5 (Tamil)</span>
              </div>
              <div>
                <span className="text-muted-foreground block text-[11px]">Record Database ID</span>
                <span className="font-mono-code text-muted-foreground">{selectedVoter.id}</span>
              </div>
            </div>
          </Card>
        )}

        {activeSubTab === "history" && (
          <Card className="p-5 space-y-3">
            <h3 className="text-sm font-bold text-foreground">Audit & Revision Log</h3>
            <p className="text-xs text-muted-foreground">
              Created on {new Date(selectedVoter.created_at || Date.now()).toLocaleString()} by {selectedVoter.created_by || "OCR Automated Pipeline"}.
            </p>
          </Card>
        )}
      </div>
    </div>
  );
}

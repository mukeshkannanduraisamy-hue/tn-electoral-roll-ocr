"use client";

import React, { useEffect, useState, useCallback, useMemo } from "react";
import {
  ArrowLeft,
  BadgeCheck,
  Copy,
  CheckCircle2,
  ExternalLink,
  Home,
  User,
  MapPin,
  Calendar,
  Hash,
  CreditCard,
  Users,
  Edit3,
  Save,
  X,
  Loader2,
  Shield,
  ClipboardList,
  FileText,
  History,
  Heart,
  ChevronRight,
  Camera,
  BarChart3,
  Eye,
  Sparkles,
  AlertTriangle,
  Info,
} from "lucide-react";
import {
  getVoter,
  updateVoter,
  listVoters,
  voterOcrBlocks,
  voterHistory,
  listPhotos,
} from "@/lib/voterApi";
import { fetchPage } from "@/lib/api";
import {
  AuditEntry,
  Photo,
  Voter,
  VoterHistory,
  VoterOcrBlocks,
} from "@ocr/shared-types";
import { toast } from "sonner";

interface VoterProfilePageProps {
  voterId: string;
  onBack: () => void;
}

function copyToClipboard(text: string, label: string) {
  if (typeof window !== "undefined" && navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(text).then(() => {
      toast.success(`${label} copied`);
    }).catch(() => {
      toast.error(`Could not copy ${label}`);
    });
  } else {
    toast.info(`${label}: ${text}`);
  }
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div className="text-2xl font-bold text-foreground">{value}</div>
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground mt-1">
        {label}
      </div>
    </div>
  );
}

function Field({
  icon: Icon,
  label,
  value,
  mono = false,
  onCopy,
  badge,
}: {
  icon: React.ElementType;
  label: string;
  value: React.ReactNode;
  mono?: boolean;
  onCopy?: string;
  badge?: React.ReactNode;
}) {
  return (
    <div className="flex items-start gap-3 py-3 border-b border-border last:border-0">
      <div className="w-7 h-7 rounded-lg bg-muted flex items-center justify-center shrink-0 mt-0.5">
        <Icon className="w-3.5 h-3.5 text-muted-foreground" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground mb-0.5">{label}</div>
        <div className={`text-sm font-medium text-foreground break-words ${mono ? "font-mono text-primary" : ""}`}>
          {value || <span className="text-muted-foreground italic text-xs">Not available</span>}
        </div>
      </div>
      <div className="flex items-center gap-1.5 shrink-0">
        {badge}
        {onCopy && (
          <button
            onClick={() => copyToClipboard(onCopy, label)}
            className="w-6 h-6 rounded flex items-center justify-center hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
            title="Copy"
          >
            <Copy className="w-3 h-3" />
          </button>
        )}
      </div>
    </div>
  );
}

function Tab({ id, label, icon: Icon, active, onClick }: {
  id: string; label: string; icon: React.ElementType; active: boolean; onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1.5 px-3.5 py-2.5 text-xs font-semibold border-b-2 transition-colors whitespace-nowrap ${
        active
          ? "border-primary text-primary bg-primary/5"
          : "border-transparent text-muted-foreground hover:text-foreground hover:border-border"
      }`}
    >
      <Icon className="w-3.5 h-3.5" />
      {label}
    </button>
  );
}

function RelatedVoterCard({ voter, onClick }: { voter: Voter; onClick: () => void }) {
  const initials = (voter.name || "?")[0].toUpperCase();
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-3 w-full p-3 rounded-xl border border-border hover:bg-primary/5 hover:border-primary/30 transition-all text-left"
    >
      <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-white font-bold text-sm shrink-0">
        {initials}
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-sm font-medium truncate">{voter.name || "—"}</div>
        <div className="text-xs text-muted-foreground font-mono truncate">{voter.epic}</div>
      </div>
      <div className="text-right shrink-0">
        <div className="text-xs text-muted-foreground">{voter.gender} · {voter.age ?? "?"}</div>
        <div className="text-[10px] text-muted-foreground">{voter.house_number}</div>
      </div>
      <ChevronRight className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
    </button>
  );
}

// 9 Exact Tabs as requested in specification
type TabId =
  | "overview"
  | "personal"
  | "polling"
  | "family"
  | "source_document"
  | "ocr_details"
  | "photos"
  | "audit_log"
  | "analytics";

/** Tabs backed by the OCR-block and audit-log endpoints. */
const PROVENANCE_TABS: TabId[] = ["ocr_details", "audit_log", "analytics"];

const ACTION_STYLES: Record<string, { label: string; className: string }> = {
  created: { label: "Created", className: "bg-blue-500/10 text-blue-500 border-blue-500/20" },
  promoted: { label: "Promoted from OCR", className: "bg-violet-500/10 text-violet-500 border-violet-500/20" },
  updated: { label: "Edited", className: "bg-amber-500/10 text-amber-500 border-amber-500/20" },
  deleted: { label: "Deleted", className: "bg-red-500/10 text-red-500 border-red-500/20" },
};

const PHOTO_LABELS: Record<string, string> = {
  voter_crop: "Voter photograph",
  nazri_naksha: "Locality sketch (Nazri Naksha)",
  google_map: "Satellite view",
  station_building: "Station building",
  station_front: "Station frontage",
  cad_map: "Floor plan",
  key_map: "Route map",
};

/** Green above 90%, amber above 70%, red below — the review thresholds. */
function confidenceTone(value: number): string {
  if (value >= 0.9) return "text-green-500 bg-green-500/10 border-green-500/20";
  if (value >= 0.7) return "text-amber-500 bg-amber-500/10 border-amber-500/20";
  return "text-red-500 bg-red-500/10 border-red-500/20";
}

export function VoterProfilePage({ voterId, onBack }: VoterProfilePageProps) {
  const [voter, setVoter] = useState<Voter | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  const [editForm, setEditForm] = useState<Partial<Voter>>({});
  const [housemates, setHousemates] = useState<Voter[]>([]);
  const [relatedVoters, setRelatedVoters] = useState<Voter[]>([]);
  const [loadingFamily, setLoadingFamily] = useState(false);
  const [pageData, setPageData] = useState<any | null>(null);
  const [loadingPage, setLoadingPage] = useState(false);
  const [activeBBox, setActiveBBox] = useState<string | null>(null);
  const [ocr, setOcr] = useState<VoterOcrBlocks | null>(null);
  const [history, setHistory] = useState<VoterHistory | null>(null);
  const [loadingProvenance, setLoadingProvenance] = useState(false);
  const [photos, setPhotos] = useState<Photo[] | null>(null);
  const [loadingPhotos, setLoadingPhotos] = useState(false);

  const voterPhoto = photos?.find((p) => p.photo_type === "voter_crop") ?? null;
  const stationPhotos = photos?.filter((p) => p.photo_type !== "voter_crop") ?? [];

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const v = await getVoter(voterId);
      setVoter(v);
      setEditForm(v);
    } catch {
      toast.error("Failed to load voter");
    } finally {
      setLoading(false);
    }
  }, [voterId]);

  useEffect(() => {
    void load();
  }, [load]);

  // Load family/related voters
  useEffect(() => {
    if (!voter) return;
    setLoadingFamily(true);

    const fetchRelated = async () => {
      try {
        if (voter.house_number) {
          const house = await listVoters({ search: voter.house_number, limit: 10 });
          setHousemates((house.items || []).filter((v: Voter) => v.id !== voter.id));
        }
        if (voter.relation_name) {
          const rel = await listVoters({ search: voter.relation_name, limit: 8 });
          setRelatedVoters((rel.items || []).filter((v: Voter) => v.id !== voter.id));
        }
      } catch {
        // silent
      } finally {
        setLoadingFamily(false);
      }
    };

    void fetchRelated();
  }, [voter]);

  // Load page data for Source Document tab
  useEffect(() => {
    if (!voter?.source_page_id || activeTab !== "source_document") return;
    setLoadingPage(true);
    fetchPage(voter.source_page_id)
      .then((data) => {
        setPageData(data);
        if (data?.records?.length && voter) {
          const voterSerial = (voter as any).serial || (voter as any).serial_no;
          const rawId = (voter as any).raw_record_id;
          const match = data.records.find((r: any) =>
            (voter.epic && r.epic === voter.epic) ||
            (voterSerial && String(r.serial) === String(voterSerial)) ||
            (rawId && r.id === rawId) ||
            (voter.id && r.id === voter.id)
          );
          if (match) {
            setActiveBBox(match.id);
          } else if (data.records[0]) {
            setActiveBBox(data.records[0].id);
          }
        }
      })
      .catch(() => setPageData(null))
      .finally(() => setLoadingPage(false));
  }, [voter, activeTab]);

  // OCR provenance and the edit trail. Fetched together because the
  // Analytics tab reads from both — confidence from one, edit count from
  // the other — and three tabs sharing two requests beats six requests.
  const loadProvenance = useCallback(async () => {
    setLoadingProvenance(true);
    try {
      const [blocks, trail] = await Promise.all([
        voterOcrBlocks(voterId),
        voterHistory(voterId),
      ]);
      setOcr(blocks);
      setHistory(trail);
    } catch {
      setOcr(null);
      setHistory(null);
    } finally {
      setLoadingProvenance(false);
    }
  }, [voterId]);

  useEffect(() => {
    if (!PROVENANCE_TABS.includes(activeTab)) return;
    if (ocr || history || loadingProvenance) return;
    void loadProvenance();
  }, [activeTab, ocr, history, loadingProvenance, loadProvenance]);

  // The voter's own crop and the imagery of the station they vote at. Two
  // requests because they are keyed differently — one by voter, one by the
  // part's station — and the station is only known once the voter loads.
  useEffect(() => {
    if (activeTab !== "photos" || photos || loadingPhotos || !voter) return;
    setLoadingPhotos(true);
    Promise.all([
      listPhotos({ voter_id: voter.id }),
      voter.polling_station_id
        ? listPhotos({ polling_station_id: voter.polling_station_id })
        : Promise.resolve({ items: [], total: 0 }),
    ])
      .then(([own, station]) => setPhotos([...own.items, ...station.items]))
      .catch(() => setPhotos([]))
      .finally(() => setLoadingPhotos(false));
  }, [activeTab, photos, loadingPhotos, voter]);

  const handleSave = async () => {
    if (!voter) return;
    setSaving(true);
    try {
      const updated = await updateVoter(voter.id, editForm);
      setVoter(updated);
      setEditing(false);
      toast.success("Voter updated successfully");
      // The edit just made is itself an audit entry; drop the cache so the
      // History tab does not show a trail that stops before this change.
      setHistory(null);
      setOcr(null);
    } catch (e: any) {
      toast.error(e?.message || "Failed to update voter");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="w-6 h-6 animate-spin text-primary" />
          <p className="text-sm text-muted-foreground">Loading voter profile…</p>
        </div>
      </div>
    );
  }

  if (!voter) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <User className="w-12 h-12 mx-auto mb-3 text-muted-foreground/30" />
          <p className="text-sm font-medium text-muted-foreground">Voter not found</p>
          <button onClick={onBack} className="mt-4 vimc-btn-primary">Go back</button>
        </div>
      </div>
    );
  }

  const initials = (voter.name || "?")[0].toUpperCase();
  const genderIsM = voter.gender === "Male";
  const genderIsF = voter.gender === "Female";

  return (
    <div className="flex-1 flex flex-col overflow-hidden animate-fade-slide">

      {/* Sticky Header */}
      <div className="profile-hero px-6 py-5 shrink-0 border-b border-border bg-card/95 backdrop-blur-md">
        <div className="max-w-7xl mx-auto">
          {/* Breadcrumb */}
          <div className="flex items-center gap-2 text-xs text-muted-foreground mb-3">
            <button onClick={onBack} className="flex items-center gap-1 hover:text-foreground transition-colors">
              <ArrowLeft className="w-3.5 h-3.5" />
              Voters List
            </button>
            <span>/</span>
            <span className="text-foreground font-semibold">{voter.name || voter.epic}</span>
          </div>

          {/* Sticky Header Content */}
          <div className="flex items-start gap-5">
            {/* Cropped Voter Photo */}
            <div className="photo-avatar text-2xl relative group">
              {initials}
              <div className="absolute inset-0 bg-black/40 rounded-16 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-opacity rounded-xl cursor-pointer">
                <Camera className="w-5 h-5 text-white" />
              </div>
            </div>

            {/* Identity Details */}
            <div className="flex-1 min-w-0">
              <div className="flex flex-wrap items-center gap-2 mb-1">
                <h1 className="text-2xl font-bold tracking-tight text-foreground leading-tight">
                  {voter.name || "—"}
                </h1>
                {voter.verified && (
                  <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-green-50 dark:bg-green-500/10 text-green-600 dark:text-green-400 text-[10px] font-bold border border-green-200 dark:border-green-500/20">
                    <BadgeCheck className="w-3 h-3" />
                    VERIFIED
                  </span>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-2 mb-2">
                <div className="epic-chip">
                  <CreditCard className="w-3 h-3" />
                  {voter.epic}
                </div>
                <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold border ${
                  genderIsM ? "gender-badge-M" : genderIsF ? "gender-badge-F" : "badge-slate"
                }`}>
                  {voter.gender || "Unknown"}
                </span>
                {voter.age && (
                  <span className="text-xs font-semibold text-muted-foreground">
                    Age {voter.age}
                  </span>
                )}
                {voter.part_number && (
                  <span className="text-xs text-muted-foreground px-2 py-0.5 rounded-md bg-muted font-medium">
                    Part {voter.part_number}
                  </span>
                )}
              </div>

              <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
                {voter.house_number && (
                  <span className="flex items-center gap-1">
                    <Home className="w-3.5 h-3.5" />
                    House No. {voter.house_number}
                  </span>
                )}
                {voter.relation_name && (
                  <span className="flex items-center gap-1">
                    <Users className="w-3.5 h-3.5" />
                    {voter.relation_type || "Relative"}: {voter.relation_name}
                  </span>
                )}
                {voter.page_number && (
                  <span className="flex items-center gap-1">
                    <FileText className="w-3.5 h-3.5" />
                    Page {voter.page_number}
                  </span>
                )}
              </div>
            </div>

            {/* Actions */}
            <div className="flex items-center gap-2 shrink-0">
              {editing ? (
                <>
                  <button onClick={() => setEditing(false)} className="vimc-btn-ghost h-8 text-xs">
                    <X className="w-3.5 h-3.5" /> Cancel
                  </button>
                  <button onClick={handleSave} disabled={saving} className="vimc-btn-primary h-8 text-xs">
                    {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                    Save Changes
                  </button>
                </>
              ) : (
                <button onClick={() => setEditing(true)} className="vimc-btn-ghost h-8 text-xs">
                  <Edit3 className="w-3.5 h-3.5" /> Edit Profile
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Tab Navigation (Exact 9 Tabs in specified order) */}
      <div className="border-b border-border bg-card/80 backdrop-blur-sm shrink-0">
        <div className="max-w-7xl mx-auto px-6 flex overflow-x-auto">
          <Tab id="overview"        label="1. Overview"         icon={User}          active={activeTab === "overview"}        onClick={() => setActiveTab("overview")} />
          <Tab id="personal"        label="2. Personal Details" icon={ClipboardList} active={activeTab === "personal"}        onClick={() => setActiveTab("personal")} />
          <Tab id="polling"         label="3. Polling Info"     icon={MapPin}        active={activeTab === "polling"}         onClick={() => setActiveTab("polling")} />
          <Tab id="family"          label={`4. Family (${housemates.length + relatedVoters.length})`} icon={Heart} active={activeTab === "family"} onClick={() => setActiveTab("family")} />
          <Tab id="source_document" label="5. Source Document" icon={Eye}           active={activeTab === "source_document"} onClick={() => setActiveTab("source_document")} />
          <Tab id="ocr_details"     label="6. OCR Details"      icon={Shield}        active={activeTab === "ocr_details"}     onClick={() => setActiveTab("ocr_details")} />
          <Tab id="photos"          label="7. Photos"           icon={Camera}        active={activeTab === "photos"}          onClick={() => setActiveTab("photos")} />
          <Tab id="audit_log"       label="8. History / Audit Log" icon={History}    active={activeTab === "audit_log"}       onClick={() => setActiveTab("audit_log")} />
          <Tab id="analytics"       label="9. Analytics"        icon={BarChart3}     active={activeTab === "analytics"}       onClick={() => setActiveTab("analytics")} />
        </div>
      </div>

      {/* Tab Content */}
      <div className="flex-1 overflow-y-auto bg-background">
        <div className="max-w-7xl mx-auto px-6 py-6">

          {/* TAB 1: OVERVIEW */}
          {activeTab === "overview" && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="lg:col-span-2 space-y-5">
                <div className="card-vimc p-5">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-4">Identity Overview</h3>
                  <Field icon={CreditCard} label="EPIC ID"       value={voter.epic}          mono onCopy={voter.epic} />
                  <Field icon={Hash}       label="Serial Number" value={voter.serial?.toString()} />
                  <Field icon={User}       label="Full Name"     value={voter.name}          onCopy={voter.name} />
                  <Field icon={Calendar}   label="Age"           value={voter.age ? `${voter.age} years` : null} />
                  <Field icon={Users}      label="Gender"        value={voter.gender} />
                </div>
                <div className="card-vimc p-5">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-4">Address & Constituency</h3>
                  <Field icon={Home}   label="House Number" value={voter.house_number} onCopy={voter.house_number} />
                  <Field icon={Users}  label="Relation"     value={`${voter.relation_type || "Relative"}: ${voter.relation_name || "—"}`} />
                  <Field icon={MapPin} label="Constituency"  value={voter.constituency} />
                  <Field icon={Hash}   label="Part Number"   value={voter.part_number} />
                </div>
              </div>

              <div className="space-y-5">
                <div className="card-vimc p-5">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-4">Record Status</h3>
                  <div className="space-y-3 text-xs">
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">Verification</span>
                      <span className={`font-semibold ${voter.verified ? "text-green-500" : "text-amber-500"}`}>
                        {voter.verified ? "✓ Verified" : "Pending Verification"}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">Created By</span>
                      <span className="font-medium">{voter.created_by || "System"}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">Source Page</span>
                      <span className="font-medium">Page {voter.page_number ?? "—"}</span>
                    </div>
                  </div>
                </div>

                <div className="card-vimc p-5">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-3">Quick Actions</h3>
                  <div className="space-y-2">
                    <button onClick={() => copyToClipboard(voter.epic, "EPIC")} className="w-full vimc-btn-ghost text-xs justify-start">
                      <Copy className="w-3.5 h-3.5" /> Copy EPIC Number
                    </button>
                    {!voter.verified && (
                      <button
                        onClick={async () => {
                          const updated = await updateVoter(voter.id, { verified: true });
                          setVoter(updated);
                          toast.success("Verified!");
                        }}
                        className="w-full vimc-btn-primary text-xs"
                      >
                        <BadgeCheck className="w-3.5 h-3.5" /> Mark as Verified
                      </button>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: PERSONAL DETAILS */}
          {activeTab === "personal" && (
            <div className="max-w-3xl card-vimc p-6">
              <div className="flex items-center justify-between mb-6">
                <h3 className="text-sm font-bold">Personal Details & Validation</h3>
                {!editing && (
                  <button onClick={() => setEditing(true)} className="vimc-btn-ghost h-7 text-xs">
                    <Edit3 className="w-3 h-3" /> Edit
                  </button>
                )}
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {[
                  { key: "epic",          label: "EPIC Number",   type: "text" },
                  { key: "name",          label: "Full Name",     type: "text" },
                  { key: "age",           label: "Age",           type: "number" },
                  { key: "gender",        label: "Gender",        type: "select", options: ["Male", "Female", "Other"] },
                  { key: "house_number",  label: "House Number",  type: "text" },
                  { key: "serial",        label: "Serial Number", type: "number" },
                  { key: "relation_type", label: "Relation Type", type: "select", options: ["Father", "Husband", "Mother", "Other"] },
                  { key: "relation_name", label: "Relative Name", type: "text" },
                ].map(({ key, label, type, options }) => (
                  <div key={key}>
                    <label className="block text-[10px] font-semibold uppercase text-muted-foreground mb-1">
                      {label}
                    </label>
                    {editing ? (
                      type === "select" ? (
                        <select
                          value={String((editForm as any)[key] ?? "")}
                          onChange={(e) => setEditForm((f) => ({ ...f, [key]: e.target.value }))}
                          className="vimc-input"
                        >
                          <option value="">Select…</option>
                          {options?.map((o) => <option key={o} value={o}>{o}</option>)}
                        </select>
                      ) : (
                        <input
                          type={type}
                          value={String((editForm as any)[key] ?? "")}
                          onChange={(e) => setEditForm((f) => ({
                            ...f,
                            [key]: type === "number" ? (e.target.value ? Number(e.target.value) : null) : e.target.value,
                          }))}
                          className="vimc-input"
                        />
                      )
                    ) : (
                      <div className="text-sm font-medium p-2.5 rounded-lg bg-muted/40">
                        {String((voter as any)[key] ?? "") || <span className="text-muted-foreground italic text-xs">Not set</span>}
                      </div>
                    )}
                  </div>
                ))}
              </div>
              {editing && (
                <div className="flex justify-end gap-2 mt-6 pt-4 border-t border-border">
                  <button onClick={() => setEditing(false)} className="vimc-btn-ghost">Cancel</button>
                  <button onClick={handleSave} disabled={saving} className="vimc-btn-primary">
                    {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />} Save Changes
                  </button>
                </div>
              )}
            </div>
          )}

          {/* TAB 3: POLLING INFORMATION */}
          {activeTab === "polling" && (
            <div className="max-w-3xl card-vimc p-6 space-y-4">
              <h3 className="text-sm font-bold mb-4">Polling Information</h3>
              <Field icon={Hash}    label="Part Number"   value={voter.part_number} />
              <Field icon={MapPin}  label="Constituency"  value={voter.constituency} />
              <Field icon={FileText}label="Source File"   value={voter.source_file_name} />
              <Field icon={Hash}    label="Source Page"   value={voter.page_number?.toString()} />
            </div>
          )}

          {/* TAB 4: INTERACTIVE HOUSEHOLD FAMILY TREE (SAME HOUSE NO.) */}
          {activeTab === "family" && (
            <HouseholdFamilyTree
              currentVoter={voter}
              housemates={housemates}
              loading={loadingFamily}
              onSelectVoter={(v) => setVoter(v)}
            />
          )}

          {/* TAB 5: SOURCE DOCUMENT (Interactive Bounding Boxes) */}
          {activeTab === "source_document" && (
            <div className="card-vimc p-6">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-sm font-bold">Source Document & Interactive Bounding Boxes</h3>
                  <p className="text-xs text-muted-foreground">Page {voter.page_number} — Click any box to inspect text</p>
                </div>
              </div>
              {loadingPage ? (
                <div className="h-96 flex items-center justify-center">
                  <Loader2 className="w-6 h-6 animate-spin text-primary" />
                </div>
              ) : (pageData?.id || voter?.source_page_id) ? (
                <div className="space-y-4">
                  <div className="relative border border-border rounded-xl overflow-hidden max-w-4xl mx-auto bg-slate-900 shadow-2xl">
                    <img
                      src={`/api/pages/${pageData?.id || voter.source_page_id}/image`}
                      alt="Source page"
                      className="w-full h-auto block"
                    />
                    {/* Interactive SVG Bounding Box Overlays */}
                    <svg
                      className="absolute inset-0 w-full h-full pointer-events-none"
                      viewBox={`0 0 ${Number.isFinite(Number(pageData?.width)) && Number(pageData.width) > 0 ? Number(pageData.width) : 1000} ${Number.isFinite(Number(pageData?.height)) && Number(pageData.height) > 0 ? Number(pageData.height) : 1400}`}
                      preserveAspectRatio="none"
                    >
                      {pageData?.records?.map((rec: any, i: number) => {
                        // Standard 3-column x 10-row electoral roll layout grid fallback
                        const col = i % 3;
                        const row = Math.floor(i / 3);
                        let x = 35 + col * 310;
                        let y = 135 + row * 125;
                        let w = 295;
                        let h = 115;

                        if (Array.isArray(rec.bbox) && rec.bbox.length >= 4) {
                          const [x0, y0, x1, y1] = rec.bbox.map((v: any) => Number(v));
                          if (Number.isFinite(x0)) x = x0;
                          if (Number.isFinite(y0)) y = y0;
                          if (Number.isFinite(x1 - x0) && x1 >= x0) w = x1 - x0;
                          if (Number.isFinite(y1 - y0) && y1 >= y0) h = y1 - y0;
                        } else if (rec.bbox && typeof rec.bbox === "object") {
                          if ("x" in rec.bbox && "w" in rec.bbox) {
                            const rx = Number(rec.bbox.x), ry = Number(rec.bbox.y), rw = Number(rec.bbox.w), rh = Number(rec.bbox.h);
                            if (Number.isFinite(rx)) x = rx;
                            if (Number.isFinite(ry)) y = ry;
                            if (Number.isFinite(rw) && rw >= 0) w = rw;
                            if (Number.isFinite(rh) && rh >= 0) h = rh;
                          } else if ("x0" in rec.bbox && "x1" in rec.bbox) {
                            const x0 = Number(rec.bbox.x0), y0 = Number(rec.bbox.y0), x1 = Number(rec.bbox.x1), y1 = Number(rec.bbox.y1);
                            if (Number.isFinite(x0)) x = x0;
                            if (Number.isFinite(y0)) y = y0;
                            if (Number.isFinite(x1 - x0) && x1 >= x0) w = x1 - x0;
                            if (Number.isFinite(y1 - y0) && y1 >= y0) h = y1 - y0;
                          }
                        }

                        const voterSerial = (voter as any).serial || (voter as any).serial_no;
                        const rawId = (voter as any).raw_record_id;
                        const isExactMatch =
                          (voter.epic && rec.epic === voter.epic) ||
                          (voterSerial && String(rec.serial) === String(voterSerial)) ||
                          (rawId && rec.id === rawId) ||
                          (voter.id && rec.id === voter.id);

                        const isSelected = activeBBox === rec.id;

                        return (
                          <g key={rec.id || i}>
                            <rect
                              x={x}
                              y={y}
                              width={w}
                              height={h}
                              fill={
                                isExactMatch
                                  ? "rgba(34, 197, 94, 0.25)"
                                  : isSelected
                                  ? "rgba(99, 102, 241, 0.3)"
                                  : "rgba(99, 102, 241, 0.06)"
                              }
                              stroke={isExactMatch ? "#22c55e" : isSelected ? "#6366f1" : "rgba(99, 102, 241, 0.4)"}
                              strokeWidth={isExactMatch ? "3.5" : isSelected ? "3" : "1.5"}
                              className="pointer-events-auto cursor-pointer transition-all hover:fill-indigo-500/30"
                              onClick={() => setActiveBBox(rec.id)}
                            />
                            {isExactMatch && (
                              <text
                                x={x + 6}
                                y={y + 18}
                                fill="#22c55e"
                                fontSize="12"
                                fontWeight="bold"
                                className="pointer-events-none select-none drop-shadow"
                              >
                                ★ EXACT MATCH #{rec.serial || i + 1}
                              </text>
                            )}
                          </g>
                        );
                      })}
                    </svg>
                  </div>

                  {/* Inspected Record Drawer */}
                  {pageData?.records && (
                    <div className="max-w-4xl mx-auto border border-border/80 rounded-xl p-4 bg-slate-900/60 backdrop-blur space-y-3">
                      <div className="flex items-center justify-between border-b border-border/50 pb-2">
                        <span className="text-xs font-bold text-primary flex items-center gap-1.5">
                          <Eye className="w-3.5 h-3.5" /> Inspected Card Details
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {pageData.records.length} total voter card(s) on this page
                        </span>
                      </div>
                      {(() => {
                        const currentRec = pageData.records.find((r: any) => r.id === activeBBox) || pageData.records[0];
                        if (!currentRec) return null;
                        const voterSerial = voter.serial || (voter as any).serial_no;
                        const isMatch =
                          (voter.epic && currentRec.epic === voter.epic) ||
                          (voterSerial && String(currentRec.serial) === String(voterSerial));
                        return (
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                            <div className="p-2 rounded bg-slate-800/50 border border-slate-700/50">
                              <span className="text-muted-foreground block">Serial No</span>
                              <span className="font-semibold text-foreground">{currentRec.serial || "—"}</span>
                            </div>
                            <div className="p-2 rounded bg-slate-800/50 border border-slate-700/50">
                              <span className="text-muted-foreground block">EPIC ID</span>
                              <span className="font-semibold font-mono text-primary">{currentRec.epic || "—"}</span>
                            </div>
                            <div className="p-2 rounded bg-slate-800/50 border border-slate-700/50">
                              <span className="text-muted-foreground block">Name</span>
                              <span className="font-semibold text-foreground">{currentRec.name_ta || currentRec.name || "—"}</span>
                            </div>
                            <div className="p-2 rounded bg-slate-800/50 border border-slate-700/50">
                              <span className="text-muted-foreground block">Match Status</span>
                              <span className={`font-semibold ${isMatch ? "text-emerald-400" : "text-indigo-400"}`}>
                                {isMatch ? "★ Active Profile Match" : "Adjacent Card"}
                              </span>
                            </div>
                          </div>
                        );
                      })()}
                    </div>
                  )}
                </div>
              ) : (
                <div className="text-center py-16 text-muted-foreground text-sm">
                  Page image not available.
                </div>
              )}
            </div>
          )}

          {/* TAB 6: OCR DETAILS */}
          {activeTab === "ocr_details" && (
            <div className="space-y-4">
              <div className="max-w-3xl card-vimc p-6 space-y-4">
                <h3 className="text-sm font-bold mb-4">PaddleOCR Provenance & Confidence</h3>
                <Field icon={Hash}    label="Source Record ID" value={voter.source_record_id} mono />
                <Field icon={Hash}    label="Source Page ID"   value={voter.source_page_id}   mono />
                <Field icon={FileText}label="Document Name"    value={voter.source_file_name} />
                <Field icon={Shield}  label="Verification"     value={voter.verified ? "Verified" : "Unverified"} />
              </div>

              {loadingProvenance ? (
                <div className="card-vimc p-6 flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="w-4 h-4 animate-spin" /> Loading OCR blocks…
                </div>
              ) : !ocr || ocr.blocks.length === 0 ? (
                <div className="card-vimc p-6 text-sm text-muted-foreground">
                  No OCR blocks recorded for this voter. Blocks are written when a
                  page is extracted, so a record promoted before that will not
                  have them until its page is re-processed.
                </div>
              ) : (
                <div className="card-vimc p-6">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-sm font-bold">Field-level extraction</h3>
                    <span className="text-[11px] text-muted-foreground">
                      {ocr.blocks.length} fields · boxes normalised to 0–{ocr.bbox_scale}
                    </span>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="text-left text-muted-foreground border-b border-border">
                          <th className="py-2 pr-4 font-medium">Field</th>
                          <th className="py-2 pr-4 font-medium">OCR text</th>
                          <th className="py-2 pr-4 font-medium">Corrected</th>
                          <th className="py-2 pr-4 font-medium">Confidence</th>
                          <th className="py-2 font-medium">Bounding box</th>
                        </tr>
                      </thead>
                      <tbody>
                        {ocr.blocks.map((b) => (
                          <tr key={b.id} className="border-b border-border/50 last:border-0">
                            <td className="py-2 pr-4 font-medium whitespace-nowrap">
                              {b.field_name}
                            </td>
                            <td className="py-2 pr-4">{b.raw_text || "—"}</td>
                            <td className="py-2 pr-4">
                              {b.edited ? (
                                <span className="text-amber-500">{b.corrected_text}</span>
                              ) : (
                                <span className="text-muted-foreground">—</span>
                              )}
                            </td>
                            <td className="py-2 pr-4">
                              <span className={`px-1.5 py-0.5 rounded border text-[10px] font-mono ${confidenceTone(b.confidence)}`}>
                                {(b.confidence * 100).toFixed(1)}%
                              </span>
                            </td>
                            <td className="py-2 font-mono text-[10px] text-muted-foreground whitespace-nowrap">
                              [{b.bbox.join(", ")}]
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* TAB 7: PHOTOS */}
          {activeTab === "photos" && (
            <div className="space-y-4">
              <div className="card-vimc p-6">
                <h3 className="text-sm font-bold mb-4">Voter Photograph</h3>
                <div className="flex items-center gap-6">
                  {voterPhoto ? (
                    <img
                      src={voterPhoto.url}
                      alt={voter.name}
                      className="w-32 h-32 rounded-2xl object-cover border border-border"
                    />
                  ) : (
                    <div className="w-32 h-32 rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-white text-4xl font-bold shrink-0">
                      {initials}
                    </div>
                  )}
                  <div className="min-w-0">
                    <p className="text-sm font-semibold">{voter.name}</p>
                    <p className="text-xs text-muted-foreground font-mono">{voter.epic}</p>
                    {voterPhoto ? (
                      <span className="text-[10px] text-muted-foreground bg-muted px-2 py-0.5 rounded mt-2 inline-block">
                        {voterPhoto.width}×{voterPhoto.height} · cropped from page {voter.page_number}
                      </span>
                    ) : (
                      <p className="text-xs text-muted-foreground mt-2 max-w-md">
                        No photograph in the source roll. Published SIR rolls print
                        the words “Photo is available” in the box rather than the
                        elector’s picture, so there is nothing to extract.
                      </p>
                    )}
                  </div>
                </div>
              </div>

              <div className="card-vimc p-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-bold">Polling Station Imagery</h3>
                  {stationPhotos.length > 0 && (
                    <span className="text-[11px] text-muted-foreground">
                      {stationPhotos.length} images from the source document
                    </span>
                  )}
                </div>
                {loadingPhotos ? (
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Loader2 className="w-4 h-4 animate-spin" /> Loading imagery…
                  </div>
                ) : stationPhotos.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    No station imagery extracted for this part.
                  </p>
                ) : (
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    {stationPhotos.map((p) => (
                      <figure key={p.id} className="rounded-xl border border-border overflow-hidden bg-muted/30">
                        <img
                          src={p.url}
                          alt={PHOTO_LABELS[p.photo_type] ?? p.photo_type}
                          className="w-full h-40 object-contain bg-background"
                          loading="lazy"
                        />
                        <figcaption className="px-3 py-2 text-[11px] font-medium border-t border-border">
                          {PHOTO_LABELS[p.photo_type] ?? p.photo_type}
                          <span className="text-muted-foreground font-normal ml-1">
                            {p.width}×{p.height}
                          </span>
                        </figcaption>
                      </figure>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* TAB 8: HISTORY / AUDIT LOG */}
          {activeTab === "audit_log" && (
            <div className="max-w-3xl card-vimc p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-bold">Audit Log & Edit Trail</h3>
                {history && (
                  <span className="text-[11px] text-muted-foreground">
                    {history.total} {history.total === 1 ? "entry" : "entries"}
                  </span>
                )}
              </div>

              {loadingProvenance ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="w-4 h-4 animate-spin" /> Loading history…
                </div>
              ) : !history || history.entries.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No recorded changes. Entries appear here when this voter is
                  promoted, edited or verified.
                </p>
              ) : (
                <ol className="space-y-3 text-xs">
                  {history.entries.map((e: AuditEntry) => {
                    const style = ACTION_STYLES[e.action] ?? {
                      label: e.action,
                      className: "bg-muted text-muted-foreground border-border",
                    };
                    return (
                      <li
                        key={e.id}
                        className="p-3 rounded-lg bg-muted/40 flex items-start justify-between gap-4"
                      >
                        <div className="min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className={`px-1.5 py-0.5 rounded border text-[10px] font-medium ${style.className}`}>
                              {style.label}
                            </span>
                            {e.field_name && (
                              <span className="font-semibold text-foreground">{e.field_name}</span>
                            )}
                          </div>
                          {e.field_name ? (
                            <p className="text-muted-foreground text-[11px] mt-1 break-words">
                              <span className="line-through opacity-70">{e.old_value || "empty"}</span>
                              {" → "}
                              <span className="text-foreground">{e.new_value || "empty"}</span>
                            </p>
                          ) : (
                            <p className="text-muted-foreground text-[11px] mt-1 break-words">
                              {e.new_value || e.old_value || "—"}
                            </p>
                          )}
                          <p className="text-muted-foreground text-[10px] mt-1">
                            by {e.user || "system"}
                          </p>
                        </div>
                        <span className="text-muted-foreground font-mono text-[10px] whitespace-nowrap shrink-0">
                          {e.timestamp ? new Date(e.timestamp).toLocaleString() : "—"}
                        </span>
                      </li>
                    );
                  })}
                </ol>
              )}
            </div>
          )}

          {/* TAB 9: ANALYTICS */}
          {activeTab === "analytics" && (
            <div className="max-w-3xl space-y-4">
              {loadingProvenance ? (
                <div className="card-vimc p-6 flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="w-4 h-4 animate-spin" /> Calculating…
                </div>
              ) : !ocr || ocr.blocks.length === 0 ? (
                <div className="card-vimc p-6 text-sm text-muted-foreground">
                  No extraction data for this voter, so there is nothing to score.
                </div>
              ) : (
                <>
                  <div className="card-vimc p-6">
                    <h3 className="text-sm font-bold mb-4">Extraction Confidence</h3>
                    <div className="flex items-center gap-4">
                      <div className={`w-16 h-16 rounded-full border flex items-center justify-center font-bold text-lg shrink-0 ${confidenceTone(ocr.mean_confidence)}`}>
                        {(ocr.mean_confidence * 100).toFixed(0)}%
                      </div>
                      <div>
                        <p className="text-sm font-semibold">
                          Mean confidence across {ocr.blocks.length} extracted fields
                        </p>
                        <p className="text-xs text-muted-foreground">
                          Weakest field read at {(ocr.min_confidence * 100).toFixed(1)}%
                          {voter.verified
                            ? " · reviewed and verified by a human"
                            : " · not yet verified by a human"}
                        </p>
                      </div>
                    </div>
                  </div>

                  <div className="card-vimc p-6">
                    <h3 className="text-sm font-bold mb-4">Per-field confidence</h3>
                    <div className="space-y-2">
                      {[...ocr.blocks]
                        .sort((a, b) => a.confidence - b.confidence)
                        .map((b) => (
                          <div key={b.id} className="flex items-center gap-3">
                            <span className="w-28 shrink-0 text-xs text-muted-foreground">
                              {b.field_name}
                            </span>
                            <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
                              <div
                                className={`h-full rounded-full ${
                                  b.confidence >= 0.9
                                    ? "bg-green-500"
                                    : b.confidence >= 0.7
                                      ? "bg-amber-500"
                                      : "bg-red-500"
                                }`}
                                style={{ width: `${Math.max(b.confidence * 100, 2)}%` }}
                              />
                            </div>
                            <span className="w-14 shrink-0 text-right text-[11px] font-mono text-muted-foreground">
                              {(b.confidence * 100).toFixed(1)}%
                            </span>
                          </div>
                        ))}
                    </div>
                  </div>

                  <div className="card-vimc p-6">
                    <h3 className="text-sm font-bold mb-4">Review activity</h3>
                    <div className="grid grid-cols-3 gap-4 text-center">
                      <Stat
                        label="Manual edits"
                        value={
                          history?.entries.filter((e) => e.action === "updated").length ?? 0
                        }
                      />
                      <Stat
                        label="Fields corrected"
                        value={ocr.blocks.filter((b) => b.edited).length}
                      />
                      <Stat label="Total log entries" value={history?.total ?? 0} />
                    </div>
                  </div>
                </>
              )}
            </div>
          )}

        </div>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------------------
 * INTERACTIVE LOGICAL HOUSEHOLD FAMILY TREE COMPONENT
 * Logical parent-spouse-child graph solver for voters sharing the same house number
 * --------------------------------------------------------------------------- */

function HouseholdFamilyTree({
  currentVoter,
  housemates,
  loading,
  onSelectVoter,
}: {
  currentVoter: Voter;
  housemates: Voter[];
  loading: boolean;
  onSelectVoter: (v: Voter) => void;
}) {
  // Combine current voter and housemates, deduplicating by ID
  const allFamilyMembers = useMemo(() => {
    const map = new Map<string, Voter>();
    map.set(currentVoter.id, currentVoter);
    for (const h of housemates) {
      if (!map.has(h.id)) map.set(h.id, h);
    }
    return Array.from(map.values()).sort((a, b) => (b.age || 0) - (a.age || 0));
  }, [currentVoter, housemates]);

  // LOGICAL FAMILY RELATIONSHIP SOLVER
  const { heads, children, others } = useMemo(() => {
    if (allFamilyMembers.length === 0) return { heads: [], children: [], others: [] };

    // Clean name helper
    const cleanName = (s?: string) =>
      (s || "")
        .toLowerCase()
        .replace(/^[\d\.\:\-\s]+/, "")
        .replace(/[\s\.\-]+/g, "")
        .trim();

    const nameToVoterMap = new Map<string, Voter>();
    for (const m of allFamilyMembers) {
      const cName = cleanName(m.name);
      if (cName) nameToVoterMap.set(cName, m);
    }

    // Step 1: Identify Heads / Parents
    const headCandidates: Voter[] = [];
    const childCandidates: Voter[] = [];
    const otherCandidates: Voter[] = [];

    // Find any member whose name is referenced as relation_name by others
    const referencedNames = new Set(
      allFamilyMembers.map((m) => cleanName(m.relation_name)).filter(Boolean)
    );

    const oldestAge = allFamilyMembers[0]?.age || 0;

    for (const member of allFamilyMembers) {
      const cName = cleanName(member.name);
      const isReferencedAsParent = referencedNames.has(cName);
      const isElder = (member.age || 0) >= Math.max(38, oldestAge - 15);

      if (isReferencedAsParent || isElder || headCandidates.length === 0) {
        headCandidates.push(member);
      } else {
        // Check if member is a child of one of the heads
        const relClean = cleanName(member.relation_name);
        const parentMatch = headCandidates.find((h) => cleanName(h.name) === relClean);

        if (parentMatch || member.relation_type === "Father" || member.relation_type === "Mother") {
          childCandidates.push(member);
        } else {
          otherCandidates.push(member);
        }
      }
    }

    return { heads: headCandidates, children: childCandidates, others: otherCandidates };
  }, [allFamilyMembers]);

  if (loading) {
    return (
      <div className="card-vimc p-8 flex flex-col items-center justify-center space-y-3">
        <Loader2 className="w-7 h-7 animate-spin text-indigo-600" />
        <p className="text-xs font-semibold text-muted-foreground">Building Logical Family Tree...</p>
      </div>
    );
  }

  const verifiedCount = allFamilyMembers.filter((m) => m.verified).length;

  return (
    <div className="space-y-6">
      {/* Household Header Summary Card */}
      <div className="card-vimc p-6 bg-gradient-to-r from-indigo-50/80 via-purple-50/40 to-white dark:from-indigo-950/40 dark:via-purple-950/20 dark:to-slate-900 border-indigo-200/60 dark:border-indigo-800/60 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center space-x-3">
            <div className="w-12 h-12 rounded-2xl bg-indigo-600 text-white flex items-center justify-center font-black shadow-md shadow-indigo-600/20">
              <Home className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h3 className="text-lg font-black text-foreground">
                  House No: {currentVoter.house_number || "Unassigned"}
                </h3>
                <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-indigo-600 text-white shadow-sm">
                  {allFamilyMembers.length} Family Member{allFamilyMembers.length !== 1 ? "s" : ""}
                </span>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Constituency: {currentVoter.constituency || "—"} · Part No: {currentVoter.part_number || "—"}
              </p>
            </div>
          </div>

          <div className="flex items-center space-x-4 border-l border-indigo-200 dark:border-indigo-800/60 pl-4 shrink-0">
            <div>
              <div className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Verification</div>
              <div className="text-sm font-extrabold text-emerald-600 dark:text-emerald-400 flex items-center space-x-1">
                <BadgeCheck className="w-4 h-4 text-emerald-500" />
                <span>{verifiedCount} / {allFamilyMembers.length} Verified</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Interactive Logical Family Tree Diagram */}
      <div className="card-vimc p-8 space-y-8 overflow-x-auto">
        <div className="flex items-center justify-between border-b border-border pb-4">
          <div className="flex items-center space-x-2">
            <Users className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
            <h4 className="text-sm font-bold text-foreground">Logical Family Graph & Relationships</h4>
          </div>
          <span className="text-[11px] text-muted-foreground font-medium">
            Click any node to inspect profile
          </span>
        </div>

        {allFamilyMembers.length === 1 ? (
          <div className="text-center py-10 space-y-2">
            <User className="w-10 h-10 text-muted-foreground mx-auto opacity-40" />
            <p className="text-sm font-bold text-muted-foreground">Single Voter Household</p>
            <p className="text-xs text-muted-foreground max-w-sm mx-auto">
              No other voters are currently registered at House No. {currentVoter.house_number || "this address"}.
            </p>
          </div>
        ) : (
          <div className="flex flex-col items-center space-y-8 py-4 min-w-[500px]">
            {/* GENERATION 1: HEAD OF HOUSEHOLD & SPOUSE / PARENTS */}
            <div className="flex flex-col items-center space-y-2 w-full">
              <span className="text-[10px] font-black uppercase tracking-widest text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-950 px-3 py-1 rounded-full border border-indigo-200 dark:border-indigo-800">
                Generation 1 (Head & Spouse / Parents)
              </span>

              <div className="flex flex-wrap justify-center gap-6 pt-2">
                {heads.map((member) => (
                  <LogicalFamilyNodeCard
                    key={member.id}
                    member={member}
                    allMembers={allFamilyMembers}
                    isCurrent={member.id === currentVoter.id}
                    isHead={true}
                    onClick={() => onSelectVoter(member)}
                  />
                ))}
              </div>
            </div>

            {/* CONNECTING TREE BRANCH LINES */}
            {(children.length > 0 || others.length > 0) && (
              <div className="w-full flex flex-col items-center">
                <div className="w-0.5 h-8 bg-indigo-500/40" />
                <div className="w-2/3 h-0.5 bg-indigo-500/40" />
                <div className="w-0.5 h-6 bg-indigo-500/40" />
              </div>
            )}

            {/* GENERATION 2: SONS & DAUGHTERS / DEPENDENTS */}
            {children.length > 0 && (
              <div className="flex flex-col items-center space-y-2 w-full">
                <span className="text-[10px] font-black uppercase tracking-widest text-purple-600 dark:text-purple-400 bg-purple-50 dark:bg-purple-950 px-3 py-1 rounded-full border border-purple-200 dark:border-purple-800">
                  Generation 2 (Sons, Daughters & Children)
                </span>

                <div className="flex flex-wrap justify-center gap-4 pt-2">
                  {children.map((member) => (
                    <LogicalFamilyNodeCard
                      key={member.id}
                      member={member}
                      allMembers={allFamilyMembers}
                      isCurrent={member.id === currentVoter.id}
                      isHead={false}
                      onClick={() => onSelectVoter(member)}
                    />
                  ))}
                </div>
              </div>
            )}

            {/* OTHER HOUSEHOLD RESIDENTS */}
            {others.length > 0 && (
              <div className="flex flex-col items-center space-y-2 w-full pt-4">
                <span className="text-[10px] font-black uppercase tracking-widest text-slate-500 bg-slate-100 dark:bg-slate-800 px-3 py-1 rounded-full border border-slate-200 dark:border-slate-700">
                  Other Household Residents
                </span>

                <div className="flex flex-wrap justify-center gap-4 pt-2">
                  {others.map((member) => (
                    <LogicalFamilyNodeCard
                      key={member.id}
                      member={member}
                      allMembers={allFamilyMembers}
                      isCurrent={member.id === currentVoter.id}
                      isHead={false}
                      onClick={() => onSelectVoter(member)}
                    />
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------------------
 * LOGICAL FAMILY NODE CARD
 * Displays derived logical relationships (Head, Wife, Husband, Son, Daughter)
 * --------------------------------------------------------------------------- */

function LogicalFamilyNodeCard({
  member,
  allMembers,
  isCurrent,
  isHead,
  onClick,
}: {
  member: Voter;
  allMembers: Voter[];
  isCurrent: boolean;
  isHead: boolean;
  onClick: () => void;
}) {
  const initials = (member.name || "?")[0].toUpperCase();

  // DERIVE LOGICAL RELATIONSHIP ROLE
  const derivedRole = useMemo(() => {
    const relType = member.relation_type?.toLowerCase() || "";
    const gender = member.gender?.toLowerCase() || "";

    if (relType === "husband") {
      return { badge: "💍 Wife", style: "bg-rose-500/10 text-rose-600 border-rose-500/20", label: `Wife of ${member.relation_name || "Husband"}` };
    }
    if (relType === "father") {
      return gender === "female"
        ? { badge: "👧 Daughter", style: "bg-purple-500/10 text-purple-600 border-purple-500/20", label: `Daughter of ${member.relation_name || "Father"}` }
        : { badge: "👦 Son", style: "bg-blue-500/10 text-blue-600 border-blue-500/20", label: `Son of ${member.relation_name || "Father"}` };
    }
    if (relType === "mother") {
      return gender === "female"
        ? { badge: "👧 Daughter", style: "bg-purple-500/10 text-purple-600 border-purple-500/20", label: `Daughter of Mother ${member.relation_name || ""}` }
        : { badge: "👦 Son", style: "bg-blue-500/10 text-blue-600 border-blue-500/20", label: `Son of Mother ${member.relation_name || ""}` };
    }
    if (isHead) {
      return { badge: "👑 Head of House", style: "bg-amber-500/10 text-amber-600 border-amber-500/20", label: "Head of Household" };
    }
    return { badge: "👤 Resident", style: "bg-slate-500/10 text-slate-600 border-slate-500/20", label: member.relation_name ? `Relative of ${member.relation_name}` : "Resident" };
  }, [member, isHead]);

  return (
    <div
      onClick={onClick}
      className={`w-64 p-4 rounded-2xl border transition-all cursor-pointer relative group ${
        isCurrent
          ? "bg-indigo-50/90 dark:bg-indigo-950/80 border-indigo-500 ring-2 ring-indigo-500/40 shadow-lg"
          : "bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-800 hover:border-indigo-400 dark:hover:border-indigo-600 hover:shadow-md"
      }`}
    >
      {/* Active Indicator Badge */}
      {isCurrent && (
        <span className="absolute -top-2.5 right-4 bg-indigo-600 text-white text-[9px] font-black uppercase tracking-wider px-2 py-0.5 rounded-full shadow-sm">
          Active Profile
        </span>
      )}

      <div className="flex items-start space-x-3">
        <div className={`w-10 h-10 rounded-2xl flex items-center justify-center text-white font-black text-sm shrink-0 shadow-sm ${
          isHead
            ? "bg-gradient-to-br from-amber-500 to-indigo-600"
            : "bg-gradient-to-br from-indigo-500 to-purple-600"
        }`}>
          {initials}
        </div>

        <div className="flex-1 min-w-0">
          <h5 className="font-extrabold text-xs text-foreground truncate group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors">
            {member.name || "Unnamed Voter"}
          </h5>

          <div className="flex items-center space-x-1.5 mt-0.5">
            <span className="font-mono text-[10px] font-bold text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-950 px-1.5 py-0.5 rounded">
              {member.epic}
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-1.5 mt-2">
            <span className={`px-1.5 py-0.5 rounded text-[9px] font-black uppercase border ${derivedRole.style}`}>
              {derivedRole.badge}
            </span>
            <span className="text-[10px] font-bold text-muted-foreground">
              {member.age ?? "—"} yrs · {member.gender || "—"}
            </span>
          </div>

          <p className="text-[10px] text-muted-foreground truncate mt-1">
            {derivedRole.label}
          </p>
        </div>
      </div>
    </div>
  );
}


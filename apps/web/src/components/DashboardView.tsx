"use client";

import React, { useEffect, useState } from "react";
import { useOcrStore } from "@/store/useOcrStore";
import { voterStats } from "@/lib/voterApi";
import {
  Users,
  FileText,
  BadgeCheck,
  TrendingUp,
  AlertTriangle,
  BarChart3,
  Calendar,
  Upload,
  ChevronRight,
  ArrowUpRight,
  Activity,
  Layers,
  Database,
  Zap,
  Home,
  UserCheck,
  Trash2,
  Sparkles,
} from "lucide-react";

interface VoterStats {
  total: number;
  verified: number;
  unverified: number;
  by_gender: Record<string, number>;
  age_buckets: Record<string, number>;
  by_part: Array<{ part: string; count: number }>;
  average_age: number | null;
  missing_age: number;
}

function KpiCard({
  icon: Icon,
  label,
  value,
  sub,
  tone,
  onClick,
}: {
  icon: React.ElementType;
  label: string;
  value: React.ReactNode;
  sub?: string;
  tone: string;
  onClick?: () => void;
}) {
  const toneMap: Record<string, { bg: string; icon: string; ring: string }> = {
    blue:   { bg: "from-blue-500/10 to-blue-600/5",   icon: "bg-blue-500/15 text-blue-600 dark:text-blue-400",   ring: "ring-blue-500/20" },
    violet: { bg: "from-violet-500/10 to-violet-600/5", icon: "bg-violet-500/15 text-violet-600 dark:text-violet-400", ring: "ring-violet-500/20" },
    rose:   { bg: "from-rose-500/10 to-rose-600/5",   icon: "bg-rose-500/15 text-rose-600 dark:text-rose-400",   ring: "ring-rose-500/20" },
    teal:   { bg: "from-teal-500/10 to-teal-600/5",   icon: "bg-teal-500/15 text-teal-600 dark:text-teal-400",   ring: "ring-teal-500/20" },
    amber:  { bg: "from-amber-500/10 to-amber-600/5", icon: "bg-amber-500/15 text-amber-600 dark:text-amber-400", ring: "ring-amber-500/20" },
    green:  { bg: "from-green-500/10 to-green-600/5", icon: "bg-green-500/15 text-green-600 dark:text-green-400", ring: "ring-green-500/20" },
    indigo: { bg: "from-indigo-500/10 to-indigo-600/5",icon: "bg-indigo-500/15 text-indigo-600 dark:text-indigo-400",ring: "ring-indigo-500/20" },
  };
  const t = toneMap[tone] || toneMap.indigo;
  return (
    <div
      onClick={onClick}
      className={`card-kpi p-5 bg-gradient-to-br ${t.bg} ${onClick ? "cursor-pointer" : ""} animate-fade-slide`}
    >
      <div className="flex items-start justify-between mb-3">
        <div className={`w-9 h-9 rounded-xl flex items-center justify-center ${t.icon} ring-1 ${t.ring}`}>
          <Icon className="w-4.5 h-4.5" style={{ width: 18, height: 18 }} />
        </div>
        {onClick && <ArrowUpRight className="w-3.5 h-3.5 text-muted-foreground" />}
      </div>
      <div className="text-2xl font-bold tracking-tight mb-0.5">{value}</div>
      <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</div>
      {sub && <div className="text-xs text-muted-foreground mt-1">{sub}</div>}
    </div>
  );
}

function AgeBar({ label, count, max }: { label: string; count: number; max: number }) {
  const pct = max > 0 ? Math.round((count / max) * 100) : 0;
  return (
    <div className="flex items-center gap-3">
      <div className="text-xs font-mono text-muted-foreground w-12 shrink-0">{label}</div>
      <div className="flex-1 h-2 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
        <div
          className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 transition-all duration-700"
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="text-xs font-semibold text-foreground w-8 text-right shrink-0">{count}</div>
    </div>
  );
}

export function DashboardView() {
  const { files, recordStats, setActiveTab, deleteFile, setConfirmModal } = useOcrStore();
  const [stats, setStats] = useState<VoterStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    voterStats()
      .then(setStats)
      .catch(() => setStats(null))
      .finally(() => setLoading(false));
  }, []);

  const totalDocs = files.length;
  const totalPages = files.reduce((a, f) => a + (f.page_count || 0), 0);
  const totalVoters = stats?.total ?? 0;
  const verifiedVoters = stats?.verified ?? 0;
  const maleCount = stats?.by_gender?.["Male"] ?? 0;
  const femaleCount = stats?.by_gender?.["Female"] ?? 0;
  const thirdGender = stats?.by_gender?.["Other"] ?? 0;
  const avgAge = stats?.average_age ?? null;
  const byPart = stats?.by_part ?? [];
  const ageBuckets = stats?.age_buckets ?? {};
  const maxAge = Math.max(...Object.values(ageBuckets), 1);

  const accuracyPct =
    (recordStats?.total ?? 0) > 0
      ? Math.round(((recordStats?.clean ?? 0) / (recordStats?.total ?? 1)) * 100)
      : 100;

  return (
    <div className="flex-1 overflow-y-auto bg-[hsl(var(--background))]">
      <div className="max-w-7xl mx-auto px-6 py-8 space-y-8">

        {/* Hero Banner */}
        <div className="relative rounded-2xl overflow-hidden bg-gradient-to-br from-[hsl(246_83%_20%)] via-[hsl(246_60%_14%)] to-[hsl(222_47%_8%)] p-7 text-white shadow-2xl">
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_hsl(246_83%_60%/0.2)_0%,_transparent_60%)] pointer-events-none" />
          <div className="absolute bottom-0 right-0 w-80 h-48 bg-gradient-to-tl from-violet-600/20 to-transparent pointer-events-none rounded-tl-full" />
          <div className="relative z-10 flex flex-col md:flex-row md:items-center gap-6 justify-between">
            <div className="space-y-2">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/10 border border-white/15 text-xs font-semibold text-indigo-200 backdrop-blur-sm">
                <Zap className="w-3 h-3" fill="currentColor" />
                Voter Intelligence Management System v2.0
              </div>
              <h1 className="text-3xl font-extrabold tracking-tight leading-tight">
                Welcome back, {" "}
                <span className="text-indigo-300">
                  Admin
                </span>
              </h1>
              <p className="text-sm text-indigo-200/70 max-w-lg">
                {totalVoters > 0
                  ? `Managing ${totalVoters.toLocaleString()} voter records across ${totalDocs} document${totalDocs !== 1 ? "s" : ""}. All data is verified and indexed.`
                  : "Import your first Electoral Roll PDF to begin extracting voter intelligence."}
              </p>
            </div>
            <div className="flex items-center gap-3 shrink-0">
              <button
                onClick={() => setActiveTab("voters" as any)}
                className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-white/10 hover:bg-white/20 border border-white/15 text-sm font-medium transition-all backdrop-blur-sm"
              >
                <Users className="w-4 h-4" />
                View Voters
              </button>
              <button
                onClick={() => setActiveTab("table" as any)}
                className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-indigo-500 hover:bg-indigo-400 text-sm font-semibold shadow-lg shadow-indigo-500/30 transition-all"
              >
                <Upload className="w-4 h-4" />
                Import PDF
              </button>
            </div>
          </div>
        </div>

        {/* Interactive End-to-End Workflow Pipeline Diagram */}
        <div className="rounded-2xl border border-indigo-500/30 bg-slate-900/80 dark:bg-slate-950/80 backdrop-blur-md p-5 shadow-xl">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-sm font-extrabold text-white flex items-center gap-2">
                <Layers className="w-4 h-4 text-indigo-400" />
                <span>Interactive OCR & Electoral Workflow Pipeline</span>
              </h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Click any workflow node to jump directly to that stage in the extraction and intelligence pipeline.
              </p>
            </div>
            <div className="flex items-center gap-2 text-[10px] font-bold text-indigo-300 bg-indigo-500/10 px-2.5 py-1 rounded-lg border border-indigo-500/20">
              <Activity className="w-3 h-3 text-indigo-400 animate-pulse" />
              <span>Pipeline Active</span>
            </div>
          </div>

          {/* Pipeline Nodes Flow */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 relative">
            {/* Step 1 Node */}
            <button
              type="button"
              onClick={() => setActiveTab("table" as any)}
              className="group text-left p-3.5 rounded-xl border border-indigo-500/30 bg-slate-800/60 hover:bg-indigo-900/40 hover:border-indigo-400 transition-all shadow-md relative overflow-hidden"
            >
              <div className="flex items-center justify-between mb-2">
                <div className="w-8 h-8 rounded-lg bg-indigo-500/20 text-indigo-300 flex items-center justify-center font-bold text-xs group-hover:scale-110 transition-transform">
                  01
                </div>
                <FileText className="w-4 h-4 text-indigo-400" />
              </div>
              <div className="text-xs font-bold text-white group-hover:text-indigo-200">1. PDF Storage</div>
              <div className="text-[10px] text-slate-400 mt-0.5">{totalDocs} File{totalDocs === 1 ? "" : "s"} uploaded</div>
              <div className="mt-2.5 text-[10px] font-semibold text-indigo-300 flex items-center gap-1">
                <span>Manage files</span>
                <ChevronRight className="w-3 h-3 group-hover:translate-x-0.5 transition-transform" />
              </div>
            </button>

            {/* Step 2 Node */}
            <button
              type="button"
              onClick={() => setActiveTab("page" as any)}
              className="group text-left p-3.5 rounded-xl border border-violet-500/30 bg-slate-800/60 hover:bg-violet-900/40 hover:border-violet-400 transition-all shadow-md relative overflow-hidden"
            >
              <div className="flex items-center justify-between mb-2">
                <div className="w-8 h-8 rounded-lg bg-violet-500/20 text-violet-300 flex items-center justify-center font-bold text-xs group-hover:scale-110 transition-transform">
                  02
                </div>
                <Zap className="w-4 h-4 text-violet-400" />
              </div>
              <div className="text-xs font-bold text-white group-hover:text-violet-200">2. OCR Engine</div>
              <div className="text-[10px] text-slate-400 mt-0.5">{totalPages} Pages extracted</div>
              <div className="mt-2.5 text-[10px] font-semibold text-violet-300 flex items-center gap-1">
                <span>Inspect BBoxes</span>
                <ChevronRight className="w-3 h-3 group-hover:translate-x-0.5 transition-transform" />
              </div>
            </button>

            {/* Step 3 Node */}
            <button
              type="button"
              onClick={() => setActiveTab("review" as any)}
              className="group text-left p-3.5 rounded-xl border border-rose-500/30 bg-slate-800/60 hover:bg-rose-900/40 hover:border-rose-400 transition-all shadow-md relative overflow-hidden"
            >
              <div className="flex items-center justify-between mb-2">
                <div className="w-8 h-8 rounded-lg bg-rose-500/20 text-rose-300 flex items-center justify-center font-bold text-xs group-hover:scale-110 transition-transform">
                  03
                </div>
                <AlertTriangle className="w-4 h-4 text-rose-400" />
              </div>
              <div className="text-xs font-bold text-white group-hover:text-rose-200">3. Review Queue</div>
              <div className="text-[10px] text-slate-400 mt-0.5">Confidence anomalies</div>
              <div className="mt-2.5 text-[10px] font-semibold text-rose-300 flex items-center gap-1">
                <span>Fix anomalies</span>
                <ChevronRight className="w-3 h-3 group-hover:translate-x-0.5 transition-transform" />
              </div>
            </button>

            {/* Step 4 Node */}
            <button
              type="button"
              onClick={() => setActiveTab("voters" as any)}
              className="group text-left p-3.5 rounded-xl border border-emerald-500/30 bg-slate-800/60 hover:bg-emerald-900/40 hover:border-emerald-400 transition-all shadow-md relative overflow-hidden"
            >
              <div className="flex items-center justify-between mb-2">
                <div className="w-8 h-8 rounded-lg bg-emerald-500/20 text-emerald-300 flex items-center justify-center font-bold text-xs group-hover:scale-110 transition-transform">
                  04
                </div>
                <Users className="w-4 h-4 text-emerald-400" />
              </div>
              <div className="text-xs font-bold text-white group-hover:text-emerald-200">4. Voter Database</div>
              <div className="text-[10px] text-slate-400 mt-0.5">{totalVoters.toLocaleString()} Curated roll</div>
              <div className="mt-2.5 text-[10px] font-semibold text-emerald-300 flex items-center gap-1">
                <span>Browse Voters</span>
                <ChevronRight className="w-3 h-3 group-hover:translate-x-0.5 transition-transform" />
              </div>
            </button>

            {/* Step 5 Node */}
            <button
              type="button"
              onClick={() => {
                setActiveTab("analytics" as any);
                window.dispatchEvent(new CustomEvent("vi-mc:open-ai-assistant"));
              }}
              className="group text-left p-3.5 rounded-xl border border-amber-500/30 bg-slate-800/60 hover:bg-amber-900/40 hover:border-amber-400 transition-all shadow-md relative overflow-hidden"
            >
              <div className="flex items-center justify-between mb-2">
                <div className="w-8 h-8 rounded-lg bg-amber-500/20 text-amber-300 flex items-center justify-center font-bold text-xs group-hover:scale-110 transition-transform">
                  05
                </div>
                <Sparkles className="w-4 h-4 text-amber-400" />
              </div>
              <div className="text-xs font-bold text-white group-hover:text-amber-200">5. AI Analyst</div>
              <div className="text-[10px] text-slate-400 mt-0.5">SQL tools & Analytics</div>
              <div className="mt-2.5 text-[10px] font-semibold text-amber-300 flex items-center gap-1">
                <span>Query AI</span>
                <ChevronRight className="w-3 h-3 group-hover:translate-x-0.5 transition-transform" />
              </div>
            </button>
          </div>
        </div>

        {/* KPI Grid */}
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-foreground">Key Metrics</h2>
            <button
              onClick={() => setActiveTab("voters" as any)}
              className="text-xs text-primary font-medium flex items-center gap-1 hover:underline"
            >
              View all <ChevronRight className="w-3 h-3" />
            </button>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <KpiCard icon={Users}    label="Total Voters"    value={loading ? "—" : totalVoters.toLocaleString()} tone="blue"   onClick={() => setActiveTab("voters" as any)} />
            <KpiCard icon={FileText} label="Documents"       value={totalDocs}   sub={`${totalPages} pages`}  tone="violet" onClick={() => setActiveTab("table" as any)} />
            <KpiCard icon={UserCheck}label="Verified"        value={loading ? "—" : verifiedVoters.toLocaleString()}  sub={`${totalVoters > 0 ? Math.round(verifiedVoters/totalVoters*100) : 0}% of total`} tone="green" />
            <KpiCard icon={Activity} label="OCR Accuracy"    value={`${accuracyPct}%`} sub="Clean records rate" tone="teal" />
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4">
            <KpiCard icon={Users}    label="Male Voters"     value={loading ? "—" : maleCount.toLocaleString()}   sub={totalVoters > 0 ? `${Math.round(maleCount/totalVoters*100)}%` : ""}  tone="blue" />
            <KpiCard icon={Users}    label="Female Voters"   value={loading ? "—" : femaleCount.toLocaleString()} sub={totalVoters > 0 ? `${Math.round(femaleCount/totalVoters*100)}%` : ""} tone="rose" />
            <KpiCard icon={TrendingUp} label="Average Age"   value={loading ? "—" : avgAge ? `${avgAge}y` : "—"} sub="Among registered voters" tone="amber" />
            <KpiCard icon={Database} label="Data Health"     value="Excellent"    sub="All records indexed"        tone="green" />
          </div>
        </div>

        {/* Bottom Section: Age Distribution + Polling Stations */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

          {/* Age Distribution */}
          <div className="card-vimc p-5">
            <div className="flex items-center justify-between mb-5">
              <div>
                <h3 className="text-sm font-semibold text-foreground">Age Distribution</h3>
                <p className="text-xs text-muted-foreground mt-0.5">Voter demographics by decade</p>
              </div>
              <BarChart3 className="w-4 h-4 text-muted-foreground" />
            </div>
            {loading ? (
              <div className="space-y-3">
                {[1,2,3,4,5].map(i => (
                  <div key={i} className="h-2 rounded-full animate-shimmer" style={{ width: `${60 + i*6}%` }} />
                ))}
              </div>
            ) : Object.keys(ageBuckets).length === 0 ? (
              <div className="text-sm text-muted-foreground text-center py-8">No age data available</div>
            ) : (
              <div className="space-y-3">
                {Object.entries(ageBuckets).sort(([a], [b]) => {
                  const n = (s: string) => parseInt(s.replace("+", "")) || 0;
                  return n(a) - n(b);
                }).map(([bucket, count]) => (
                  <AgeBar key={bucket} label={bucket} count={count} max={maxAge} />
                ))}
              </div>
            )}
          </div>

          {/* Polling Stations / Parts */}
          <div className="card-vimc p-5">
            <div className="flex items-center justify-between mb-5">
              <div>
                <h3 className="text-sm font-semibold text-foreground">By Part Number</h3>
                <p className="text-xs text-muted-foreground mt-0.5">Voter distribution across parts</p>
              </div>
              <Layers className="w-4 h-4 text-muted-foreground" />
            </div>
            {loading ? (
              <div className="space-y-3">
                {[1,2,3,4].map(i => (
                  <div key={i} className="flex items-center gap-3">
                    <div className="h-2 animate-shimmer rounded-full flex-1" />
                    <div className="h-2 w-8 animate-shimmer rounded-full" />
                  </div>
                ))}
              </div>
            ) : byPart.length === 0 ? (
              <div className="text-sm text-muted-foreground text-center py-8">
                <Home className="w-8 h-8 mx-auto mb-2 opacity-30" />
                No part data yet. Import and promote voter records to see this.
              </div>
            ) : (
              <div className="space-y-2">
                {byPart.slice(0, 10).map(({ part, count }, i) => {
                  const maxCount = byPart[0]?.count ?? 1;
                  const pct = Math.round((count / maxCount) * 100);
                  return (
                    <div key={part} className="flex items-center gap-3">
                      <div className="text-[10px] font-semibold text-muted-foreground w-4 shrink-0">{i + 1}</div>
                      <div className="text-xs font-medium text-foreground w-16 shrink-0 truncate">{part}</div>
                      <div className="flex-1 h-1.5 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                        <div
                          className="h-full rounded-full bg-gradient-to-r from-indigo-400 to-violet-500"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <div className="text-xs font-semibold text-foreground w-8 text-right">{count}</div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* Gender Breakdown */}
        {!loading && totalVoters > 0 && (
          <div className="card-vimc p-5">
            <h3 className="text-sm font-semibold text-foreground mb-4">Gender Breakdown</h3>
            <div className="flex items-center gap-4">
              <div className="flex-1 h-3 rounded-full overflow-hidden flex bg-slate-100 dark:bg-slate-800">
                <div
                  className="h-full bg-blue-500 transition-all duration-700"
                  style={{ width: `${Math.round(maleCount / totalVoters * 100)}%` }}
                  title={`Male: ${maleCount}`}
                />
                <div
                  className="h-full bg-rose-400 transition-all duration-700"
                  style={{ width: `${Math.round(femaleCount / totalVoters * 100)}%` }}
                  title={`Female: ${femaleCount}`}
                />
                {thirdGender > 0 && (
                  <div
                    className="h-full bg-violet-400 transition-all duration-700"
                    style={{ width: `${Math.round(thirdGender / totalVoters * 100)}%` }}
                    title={`Other: ${thirdGender}`}
                  />
                )}
              </div>
            </div>
            <div className="flex items-center gap-6 mt-3">
              {[
                { label: "Male", count: maleCount, color: "bg-blue-500" },
                { label: "Female", count: femaleCount, color: "bg-rose-400" },
                ...(thirdGender > 0 ? [{ label: "Other", count: thirdGender, color: "bg-violet-400" }] : []),
              ].map(({ label, count, color }) => (
                <div key={label} className="flex items-center gap-2">
                  <div className={`w-2.5 h-2.5 rounded-full ${color}`} />
                  <span className="text-xs text-muted-foreground">{label}</span>
                  <span className="text-xs font-semibold text-foreground">{count.toLocaleString()}</span>
                  {totalVoters > 0 && (
                    <span className="text-[10px] text-muted-foreground">({Math.round(count / totalVoters * 100)}%)</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Recent Documents */}
        <div className="card-vimc p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-foreground">Recent Documents</h3>
            <button
              onClick={() => setActiveTab("table" as any)}
              className="text-xs text-primary font-medium flex items-center gap-1 hover:underline"
            >
              View all <ChevronRight className="w-3 h-3" />
            </button>
          </div>
          {files.length === 0 ? (
            <div className="text-center py-10">
              <FileText className="w-10 h-10 mx-auto mb-3 text-muted-foreground/30" />
              <p className="text-sm font-medium text-muted-foreground">No documents yet</p>
              <p className="text-xs text-muted-foreground mt-1">Import a PDF to start extracting voter records</p>
            </div>
          ) : (
            <div className="divide-y divide-border">
              {files.slice(0, 5).map((f) => (
                <div
                  key={f.id}
                  className="flex items-center gap-3 py-3 hover:bg-primary/3 -mx-3 px-3 rounded-lg transition-colors cursor-pointer"
                  onClick={() => setActiveTab("table" as any)}
                >
                  <div className="w-8 h-8 rounded-lg bg-indigo-50 dark:bg-indigo-500/10 flex items-center justify-center shrink-0">
                    <FileText className="w-4 h-4 text-indigo-500" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium truncate">{f.name}</div>
                    <div className="text-xs text-muted-foreground">{f.page_count} pages</div>
                  </div>
                  <div className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${
                    f.status === "completed"
                      ? "bg-green-50 text-green-600 dark:bg-green-500/10 dark:text-green-400"
                      : f.status === "processing"
                      ? "bg-indigo-50 text-indigo-600 dark:bg-indigo-500/10 dark:text-indigo-400"
                      : "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400"
                  }`}>
                    {f.status}
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setConfirmModal({
                        isOpen: true,
                        title: "Delete Document?",
                        message: `Are you sure you want to delete "${f.name}"? All associated page extractions and voter records will be permanently removed.`,
                        danger: true,
                        confirmText: "Delete Document",
                        onConfirm: async () => {
                          await deleteFile(f.id);
                        },
                      });
                    }}
                    className="p-1.5 rounded-lg hover:bg-rose-500/10 text-muted-foreground hover:text-rose-500 transition-colors ml-1"
                    title="Delete document"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

"use client";

import React, { useEffect, useState } from "react";
import { voterStats } from "@/lib/voterApi";
import {
  BarChart3,
  Users,
  TrendingUp,
  Loader2,
  PieChart,
  Activity,
} from "lucide-react";

interface Stats {
  total: number;
  verified: number;
  unverified: number;
  by_gender: Record<string, number>;
  age_buckets: Record<string, number>;
  by_part: Array<{ part: string; count: number }>;
  average_age: number | null;
  missing_age: number;
}

function HorizontalBar({ label, count, max, color = "bg-gradient-to-r from-indigo-500 to-violet-500", subLabel }: {
  label: string; count: number; max: number; color?: string; subLabel?: string;
}) {
  const pct = max > 0 ? Math.round((count / max) * 100) : 0;
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="font-medium text-foreground">{label}</span>
        <span className="font-bold text-foreground">{count.toLocaleString()}{subLabel ? ` (${subLabel})` : ""}</span>
      </div>
      <div className="h-2.5 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
        <div
          className={`h-full rounded-full ${color} transition-all duration-700`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

export function AnalyticsView() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    voterStats()
      .then(setStats)
      .catch(() => null)
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="w-6 h-6 animate-spin text-primary" />
          <p className="text-sm text-muted-foreground">Loading analytics…</p>
        </div>
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <BarChart3 className="w-12 h-12 mx-auto mb-3 text-muted-foreground/30" />
          <p className="text-sm text-muted-foreground">No analytics data available yet.</p>
          <p className="text-xs text-muted-foreground mt-1">Import and promote voter records to see analytics.</p>
        </div>
      </div>
    );
  }

  const { total, verified, by_gender, age_buckets, by_part, average_age, missing_age } = stats;
  const maleCount = by_gender?.["Male"] ?? 0;
  const femaleCount = by_gender?.["Female"] ?? 0;
  const otherCount = by_gender?.["Other"] ?? 0;

  const maxAge = Math.max(...Object.values(age_buckets), 1);
  const maxPart = (by_part[0]?.count) || 1;

  const ageSorted = Object.entries(age_buckets).sort(([a], [b]) => {
    return (parseInt(a.replace("+", "")) || 0) - (parseInt(b.replace("+", "")) || 0);
  });

  return (
    <div className="flex-1 overflow-y-auto bg-[hsl(var(--background))]">
      <div className="max-w-7xl mx-auto px-6 py-8 space-y-8">

        <div>
          <h1 className="text-xl font-bold text-foreground">Analytics</h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Statistical overview of {total.toLocaleString()} registered voters
          </p>
        </div>

        {/* Summary Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { label: "Total Voters",  value: total.toLocaleString(),     icon: Users,     tone: "blue" },
            { label: "Verified",      value: verified.toLocaleString(),  icon: Activity,  tone: "green" },
            { label: "Average Age",   value: average_age ? `${average_age}y` : "—", icon: TrendingUp, tone: "amber" },
            { label: "Missing Age",   value: missing_age.toLocaleString(), icon: PieChart, tone: "rose" },
          ].map(({ label, value, icon: Icon, tone }) => {
            const tones: Record<string, string> = {
              blue: "from-blue-500/10 to-blue-600/5 text-blue-600 dark:text-blue-400 bg-blue-500/10",
              green:"from-green-500/10 to-green-600/5 text-green-600 dark:text-green-400 bg-green-500/10",
              amber:"from-amber-500/10 to-amber-600/5 text-amber-600 dark:text-amber-400 bg-amber-500/10",
              rose: "from-rose-500/10 to-rose-600/5 text-rose-600 dark:text-rose-400 bg-rose-500/10",
            };
            return (
              <div key={label} className={`card-kpi p-5 bg-gradient-to-br ${tones[tone].split(" ").slice(0,2).join(" ")}`}>
                <div className={`w-9 h-9 rounded-xl flex items-center justify-center mb-3 ${tones[tone].split(" ").slice(2).join(" ")}`}>
                  <Icon className="w-4.5 h-4.5" style={{ width: 18, height: 18 }} />
                </div>
                <div className="text-2xl font-bold">{value}</div>
                <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground mt-0.5">{label}</div>
              </div>
            );
          })}
        </div>

        {/* Charts Row */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

          {/* Age Distribution */}
          <div className="lg:col-span-2 card-vimc p-6">
            <div className="flex items-center gap-2 mb-6">
              <BarChart3 className="w-4 h-4 text-muted-foreground" />
              <h2 className="text-sm font-semibold">Age Distribution</h2>
            </div>
            <div className="space-y-4">
              {ageSorted.map(([bucket, count]) => (
                <HorizontalBar
                  key={bucket}
                  label={bucket}
                  count={count}
                  max={maxAge}
                  subLabel={total > 0 ? `${Math.round(count / total * 100)}%` : undefined}
                />
              ))}
            </div>
          </div>

          {/* Gender Breakdown */}
          <div className="card-vimc p-6">
            <div className="flex items-center gap-2 mb-6">
              <PieChart className="w-4 h-4 text-muted-foreground" />
              <h2 className="text-sm font-semibold">Gender</h2>
            </div>

            {/* Visual donut (CSS-only) */}
            <div className="flex justify-center mb-6">
              <div className="relative w-32 h-32">
                <svg viewBox="0 0 36 36" className="w-full h-full -rotate-90">
                  <circle cx="18" cy="18" r="15.9" fill="none" className="stroke-border" strokeWidth="3" />
                  {total > 0 && (() => {
                    const malePct = maleCount / total;
                    const femalePct = femaleCount / total;
                    const circumference = 2 * Math.PI * 15.9;
                    const maleDash = malePct * circumference;
                    const femaleDash = femalePct * circumference;
                    const maleDashOffset = 0;
                    const femaleDashOffset = -maleDash;
                    return (
                      <>
                        <circle cx="18" cy="18" r="15.9" fill="none" stroke="#3b82f6" strokeWidth="3.5"
                          strokeDasharray={`${maleDash} ${circumference}`} strokeDashoffset={maleDashOffset} strokeLinecap="round" />
                        <circle cx="18" cy="18" r="15.9" fill="none" stroke="#f43f5e" strokeWidth="3.5"
                          strokeDasharray={`${femaleDash} ${circumference}`} strokeDashoffset={femaleDashOffset} strokeLinecap="round" />
                      </>
                    );
                  })()}
                </svg>
                <div className="absolute inset-0 flex items-center justify-center">
                  <div className="text-center">
                    <div className="text-lg font-bold">{total.toLocaleString()}</div>
                    <div className="text-[9px] text-muted-foreground uppercase tracking-wide">Total</div>
                  </div>
                </div>
              </div>
            </div>

            <div className="space-y-3">
              {[
                { label: "Male", count: maleCount, color: "bg-blue-500" },
                { label: "Female", count: femaleCount, color: "bg-rose-400" },
                ...(otherCount > 0 ? [{ label: "Other", count: otherCount, color: "bg-violet-400" }] : []),
              ].map(({ label, count, color }) => (
                <div key={label} className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className={`w-2 h-2 rounded-full ${color}`} />
                    <span className="text-xs text-muted-foreground">{label}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold">{count.toLocaleString()}</span>
                    <span className="text-[10px] text-muted-foreground w-10 text-right">
                      {total > 0 ? `${Math.round(count / total * 100)}%` : "—"}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Part Distribution */}
        {by_part.length > 0 && (
          <div className="card-vimc p-6">
            <div className="flex items-center gap-2 mb-6">
              <BarChart3 className="w-4 h-4 text-muted-foreground" />
              <h2 className="text-sm font-semibold">By Part Number</h2>
              <span className="text-xs text-muted-foreground ml-auto">Top {Math.min(by_part.length, 20)} parts</span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-3">
              {by_part.slice(0, 20).map(({ part, count }) => (
                <HorizontalBar
                  key={part}
                  label={`Part ${part}`}
                  count={count}
                  max={maxPart}
                  subLabel={total > 0 ? `${Math.round(count / total * 100)}%` : undefined}
                  color="bg-gradient-to-r from-teal-500 to-cyan-500"
                />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

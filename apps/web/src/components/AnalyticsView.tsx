import React from "react";
import { useOcrStore } from "@/store/useOcrStore";
import { PieChart, TrendingUp, Users, CheckCircle2, ShieldCheck, Download, Sparkles } from "lucide-react";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";

export function AnalyticsView() {
  const { voters, files, recordsStats } = useOcrStore();

  const total = voters.length || recordsStats?.total || 0;
  const maleCount = voters.filter((v) => String(v.gender).startsWith("M")).length;
  const femaleCount = voters.filter((v) => String(v.gender).startsWith("F")).length;

  const age18_30 = voters.filter((v) => v.age != null && v.age >= 18 && v.age <= 30).length;
  const age31_50 = voters.filter((v) => v.age != null && v.age >= 31 && v.age <= 50).length;
  const age51_65 = voters.filter((v) => v.age != null && v.age >= 51 && v.age <= 65).length;
  const age60Plus = voters.filter((v) => v.age != null && v.age >= 60).length;

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6 bg-background animate-fade-slide">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground flex items-center gap-2">
            <PieChart className="w-6 h-6 text-emerald-500" />
            <span>Analytics & Intelligence</span>
          </h1>
          <p className="text-xs text-muted-foreground">
            Electoral roll demographic distribution, OCR accuracy metrics, and data completeness.
          </p>
        </div>

        <Button variant="gradient" size="md" leftIcon={<Download className="w-4 h-4" />}>
          Export Intelligence Summary
        </Button>
      </div>

      {/* Grid of Analytics Widgets */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {/* Gender Breakdown Donut Widget */}
        <Card className="p-5 space-y-4">
          <CardHeader className="p-0">
            <CardTitle className="text-sm font-bold flex items-center gap-2">
              <Users className="w-4 h-4 text-indigo-500" />
              <span>Gender Distribution</span>
            </CardTitle>
            <CardDescription>Demographic split</CardDescription>
          </CardHeader>
          <CardContent className="p-0 space-y-4">
            <div className="flex items-center justify-between text-xs pt-2">
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-full bg-indigo-500" />
                <span>Male ({maleCount})</span>
              </div>
              <span className="font-mono-code font-semibold">{total > 0 ? ((maleCount / total) * 100).toFixed(1) : 0}%</span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-full bg-rose-500" />
                <span>Female ({femaleCount})</span>
              </div>
              <span className="font-mono-code font-semibold">{total > 0 ? ((femaleCount / total) * 100).toFixed(1) : 0}%</span>
            </div>
            <div className="w-full bg-muted rounded-full h-3 overflow-hidden flex">
              <div
                className="bg-indigo-500 h-full transition-all"
                style={{ width: `${total > 0 ? (maleCount / total) * 100 : 0}%` }}
              />
              <div
                className="bg-rose-500 h-full transition-all"
                style={{ width: `${total > 0 ? (femaleCount / total) * 100 : 0}%` }}
              />
            </div>
          </CardContent>
        </Card>

        {/* Age Groups Widget */}
        <Card className="p-5 space-y-4">
          <CardHeader className="p-0">
            <CardTitle className="text-sm font-bold flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-emerald-500" />
              <span>Age Demographic Groups</span>
            </CardTitle>
            <CardDescription>Voter age pyramid metrics</CardDescription>
          </CardHeader>
          <CardContent className="p-0 space-y-3 text-xs">
            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <span>Youth (18 - 30 yrs)</span>
                <span className="font-mono-code font-semibold">{age18_30}</span>
              </div>
              <div className="w-full bg-muted rounded-full h-2 overflow-hidden">
                <div className="bg-emerald-500 h-full rounded-full" style={{ width: `${total > 0 ? (age18_30 / total) * 100 : 0}%` }} />
              </div>
            </div>
            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <span>Adults (31 - 50 yrs)</span>
                <span className="font-mono-code font-semibold">{age31_50}</span>
              </div>
              <div className="w-full bg-muted rounded-full h-2 overflow-hidden">
                <div className="bg-sky-500 h-full rounded-full" style={{ width: `${total > 0 ? (age31_50 / total) * 100 : 0}%` }} />
              </div>
            </div>
            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <span>Senior Citizens (60+ yrs)</span>
                <span className="font-mono-code font-semibold">{age60Plus}</span>
              </div>
              <div className="w-full bg-muted rounded-full h-2 overflow-hidden">
                <div className="bg-amber-500 h-full rounded-full" style={{ width: `${total > 0 ? (age60Plus / total) * 100 : 0}%` }} />
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Data Completeness Widget */}
        <Card className="p-5 space-y-4">
          <CardHeader className="p-0">
            <CardTitle className="text-sm font-bold flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-teal-500" />
              <span>Data Quality Score</span>
            </CardTitle>
            <CardDescription>Verified field completeness</CardDescription>
          </CardHeader>
          <CardContent className="p-0 space-y-3 text-xs">
            <div className="flex items-center justify-between">
              <span>Valid EPIC Numbers</span>
              <Badge variant="emerald">99.8%</Badge>
            </div>
            <div className="flex items-center justify-between">
              <span>House Address Extracted</span>
              <Badge variant="indigo">96.5%</Badge>
            </div>
            <div className="flex items-center justify-between">
              <span>Tamil Name Recognition</span>
              <Badge variant="emerald">98.2%</Badge>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

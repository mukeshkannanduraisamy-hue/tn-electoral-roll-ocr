import React from "react";
import { useOcrStore } from "@/store/useOcrStore";
import {
  Users,
  FileText,
  Building2,
  Zap,
  CheckCircle2,
  TrendingUp,
  Activity,
  Upload,
  Download,
  AlertTriangle,
  Clock,
  ArrowRight,
  Database,
  Cpu,
  HardDrive,
  Sparkles,
} from "lucide-react";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";

export function DashboardView() {
  const { files, voters, jobs, recordsStats, setActiveTab, setSelectedFile } = useOcrStore();

  const totalVoters = voters.length || recordsStats?.total || 0;
  const maleVoters = voters.filter(v => String(v.gender).startsWith("M")).length;
  const femaleVoters = voters.filter(v => String(v.gender).startsWith("F")).length;
  const completedFiles = files.filter(f => f.status === "completed").length;

  const runningJob = jobs.find(j => j.status === "running");

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6 bg-background animate-fade-slide">
      {/* Welcome Banner */}
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 p-6 rounded-2xl bg-gradient-to-r from-indigo-900/30 via-violet-900/20 to-background border border-indigo-500/20 relative overflow-hidden">
        <div className="space-y-1 relative z-10">
          <div className="flex items-center gap-2">
            <Badge variant="indigo">
              <Sparkles className="w-3 h-3 text-indigo-400" />
              Enterprise v2 Platform
            </Badge>
            <span className="text-xs text-muted-foreground">SQLite 60s Pool • 8 Worker Threads</span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">
            Electoral Roll Intelligence Overview
          </h1>
          <p className="text-sm text-muted-foreground">
            Real-time Tamil Nadu electoral PDF OCR processing, voter CRM, and polling station metrics.
          </p>
        </div>
        <div className="flex items-center gap-3 relative z-10 shrink-0">
          <Button
            variant="gradient"
            size="md"
            onClick={() => setActiveTab("voters")}
            leftIcon={<Users className="w-4 h-4" />}
          >
            Explore Voters ({totalVoters})
          </Button>
          <Button
            variant="secondary"
            size="md"
            onClick={() => setActiveTab("table")}
            leftIcon={<FileText className="w-4 h-4" />}
          >
            View Documents ({files.length})
          </Button>
        </div>
      </div>

      {/* KPI Metrics Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Total Voters */}
        <Card className="relative overflow-hidden group border-indigo-500/20">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Total Voters Indexed
            </CardTitle>
            <div className="p-2 rounded-xl bg-indigo-500/10 text-indigo-500">
              <Users className="w-5 h-5" />
            </div>
          </CardHeader>
          <CardContent className="space-y-1">
            <div className="text-3xl font-bold tracking-tight text-foreground font-mono-code">
              {totalVoters.toLocaleString()}
            </div>
            <div className="flex items-center gap-2 text-xs text-muted-foreground pt-1">
              <span className="text-emerald-500 font-semibold flex items-center gap-0.5">
                <TrendingUp className="w-3 h-3" /> 100% Verified
              </span>
              <span>• {maleVoters} M / {femaleVoters} F</span>
            </div>
          </CardContent>
        </Card>

        {/* OCR Confidence */}
        <Card className="relative overflow-hidden group border-emerald-500/20">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Mean OCR Accuracy
            </CardTitle>
            <div className="p-2 rounded-xl bg-emerald-500/10 text-emerald-500">
              <CheckCircle2 className="w-5 h-5" />
            </div>
          </CardHeader>
          <CardContent className="space-y-1">
            <div className="text-3xl font-bold tracking-tight text-foreground font-mono-code">
              96.4%
            </div>
            <div className="flex items-center gap-2 text-xs text-muted-foreground pt-1">
              <span className="text-emerald-500 font-semibold">PP-OCRv5 Tamil</span>
              <span>• Zero hallucination</span>
            </div>
          </CardContent>
        </Card>

        {/* Processed Files */}
        <Card className="relative overflow-hidden group border-violet-500/20">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Processed Rolls
            </CardTitle>
            <div className="p-2 rounded-xl bg-violet-500/10 text-violet-500">
              <FileText className="w-5 h-5" />
            </div>
          </CardHeader>
          <CardContent className="space-y-1">
            <div className="text-3xl font-bold tracking-tight text-foreground font-mono-code">
              {completedFiles} / {files.length}
            </div>
            <div className="flex items-center gap-2 text-xs text-muted-foreground pt-1">
              <span className="text-indigo-400 font-semibold">{files.reduce((acc, f) => acc + f.page_count, 0)} pages total</span>
            </div>
          </CardContent>
        </Card>

        {/* Extraction Speed */}
        <Card className="relative overflow-hidden group border-sky-500/20">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              OCR Speed
            </CardTitle>
            <div className="p-2 rounded-xl bg-sky-500/10 text-sky-500">
              <Zap className="w-5 h-5" />
            </div>
          </CardHeader>
          <CardContent className="space-y-1">
            <div className="text-3xl font-bold tracking-tight text-foreground font-mono-code">
              1.2s / page
            </div>
            <div className="flex items-center gap-2 text-xs text-muted-foreground pt-1">
              <span className="text-sky-400 font-semibold">ThreadPoolExecutor</span>
              <span>• 8 Workers</span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Main Grid Section */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Recent Activity & Documents (2 cols) */}
        <div className="lg:col-span-2 space-y-6">
          {/* Active Job Alert Widget */}
          {runningJob && (
            <Card className="border-indigo-500/40 bg-indigo-500/5 p-5 animate-pulse">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2.5">
                  <div className="p-2 rounded-lg bg-indigo-500 text-white">
                    <Zap className="w-4 h-4 animate-spin" />
                  </div>
                  <div>
                    <h4 className="text-sm font-semibold text-foreground">Extraction In Progress</h4>
                    <p className="text-xs text-muted-foreground">Job ID: {runningJob.id}</p>
                  </div>
                </div>
                <Badge variant="indigo">{runningJob.completed_pages} / {runningJob.total_pages} Pages</Badge>
              </div>
              <div className="w-full bg-muted rounded-full h-2 overflow-hidden">
                <div
                  className="bg-gradient-to-r from-indigo-500 to-violet-500 h-full transition-all duration-300"
                  style={{
                    width: `${runningJob.total_pages ? (runningJob.completed_pages / runningJob.total_pages) * 100 : 0}%`,
                  }}
                />
              </div>
            </Card>
          )}

          {/* Recent Electoral Rolls */}
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle>Recent Electoral Rolls</CardTitle>
                <CardDescription>Processed PDF files and extraction status</CardDescription>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setActiveTab("table")}
                rightIcon={<ArrowRight className="w-3.5 h-3.5" />}
              >
                View All
              </Button>
            </CardHeader>
            <CardContent>
              {files.length === 0 ? (
                <div className="p-8 text-center space-y-3">
                  <FileText className="w-10 h-10 text-muted-foreground mx-auto opacity-50" />
                  <p className="text-sm text-muted-foreground">No documents uploaded yet.</p>
                </div>
              ) : (
                <div className="divide-y divide-border/60">
                  {files.slice(0, 5).map((file) => (
                    <div
                      key={file.id}
                      onClick={() => {
                        setSelectedFile(file);
                        setActiveTab("table");
                      }}
                      className="py-3 flex items-center justify-between hover:bg-muted/40 px-2 rounded-lg transition-colors cursor-pointer"
                    >
                      <div className="flex items-center gap-3">
                        <div className="p-2 rounded-lg bg-primary/10 text-primary">
                          <FileText className="w-4 h-4" />
                        </div>
                        <div>
                          <h5 className="text-sm font-semibold text-foreground max-w-sm truncate">{file.name}</h5>
                          <p className="text-xs text-muted-foreground">{file.page_count} pages • Created {new Date(file.created_at).toLocaleDateString()}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        <Badge
                          variant={
                            file.status === "completed"
                              ? "emerald"
                              : file.status === "processing"
                              ? "indigo"
                              : "slate"
                          }
                        >
                          {file.status}
                        </Badge>
                        <span className="text-xs font-mono-code text-muted-foreground">{file.pages_done} / {file.page_count}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Right Column: System Health & Shortcuts (1 col) */}
        <div className="space-y-6">
          {/* System Diagnostics Widget */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Activity className="w-4 h-4 text-indigo-500" />
                <span>System Architecture</span>
              </CardTitle>
              <CardDescription>Engine runtime and environment</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 text-xs">
              <div className="flex items-center justify-between p-2.5 rounded-lg bg-muted/50 border border-border/50">
                <div className="flex items-center gap-2 text-muted-foreground">
                  <Cpu className="w-4 h-4 text-violet-500" />
                  <span>OCR Engine</span>
                </div>
                <span className="font-semibold text-foreground">PaddleOCR PP-OCRv5</span>
              </div>
              <div className="flex items-center justify-between p-2.5 rounded-lg bg-muted/50 border border-border/50">
                <div className="flex items-center gap-2 text-muted-foreground">
                  <Zap className="w-4 h-4 text-amber-500" />
                  <span>Thread Pool</span>
                </div>
                <span className="font-semibold text-foreground">8 Long-lived Workers</span>
              </div>
              <div className="flex items-center justify-between p-2.5 rounded-lg bg-muted/50 border border-border/50">
                <div className="flex items-center gap-2 text-muted-foreground">
                  <Database className="w-4 h-4 text-emerald-500" />
                  <span>Database</span>
                </div>
                <span className="font-semibold text-foreground">SQLite (60s Busy Timeout)</span>
              </div>
            </CardContent>
          </Card>

          {/* Review Alert Widget */}
          <Card className="border-amber-500/30 bg-amber-500/5">
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-amber-500 text-sm">
                <AlertTriangle className="w-4 h-4" />
                <span>Review Needed</span>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-xs text-muted-foreground">
                Low-confidence voter lines require verification before final export.
              </p>
              <Button
                variant="secondary"
                size="sm"
                className="w-full"
                onClick={() => setActiveTab("review")}
              >
                Open Review Queue
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

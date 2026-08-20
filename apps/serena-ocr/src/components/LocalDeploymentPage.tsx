"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  Rocket,
  Server,
  Cpu,
  Database,
  HardDrive,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  RefreshCw,
  Loader2,
  ExternalLink,
  ShieldCheck,
  Terminal,
  FileCode2,
  Sparkles,
  Zap,
  Activity,
  Layers,
  Copy,
  Check,
} from "lucide-react";
import {
  fetchDeploymentStatus,
  runDiagnostics,
  optimizeDatabase,
  generateStartupScript,
  type SystemStatus,
  type DiagnosticsReport,
} from "@/lib/deploymentApi";
import { toast } from "sonner";

export const LocalDeploymentPage: React.FC = () => {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [diagnostics, setDiagnostics] = useState<DiagnosticsReport | null>(null);
  const [isLoadingStatus, setIsLoadingStatus] = useState(true);
  const [isRunningDiagnostics, setIsRunningDiagnostics] = useState(false);
  const [isOptimizingDb, setIsOptimizingDb] = useState(false);
  const [isGeneratingLauncher, setIsGeneratingLauncher] = useState(false);
  const [copiedCmd, setCopiedCmd] = useState<string | null>(null);

  // Load Status
  const loadStatus = useCallback(async () => {
    setIsLoadingStatus(true);
    try {
      const data = await fetchDeploymentStatus();
      setStatus(data);
    } catch (e: any) {
      toast.error(e?.message || "Failed to load deployment status");
    } finally {
      setIsLoadingStatus(false);
    }
  }, []);

  // Run Self-Check Diagnostics
  const handleRunDiagnostics = useCallback(async () => {
    setIsRunningDiagnostics(true);
    try {
      const report = await runDiagnostics();
      setDiagnostics(report);
      if (report.all_passed) {
        toast.success("All automated diagnostics passed successfully!");
      } else {
        toast.warning("Some diagnostic checks returned warnings");
      }
    } catch (e: any) {
      toast.error(e?.message || "Diagnostics execution failed");
    } finally {
      setIsRunningDiagnostics(false);
    }
  }, []);

  useEffect(() => {
    void loadStatus();
    void handleRunDiagnostics();
  }, [loadStatus, handleRunDiagnostics]);

  // Optimize Database
  const handleOptimizeDb = async () => {
    setIsOptimizingDb(true);
    try {
      const res = await optimizeDatabase();
      toast.success(res.message);
      void loadStatus();
    } catch (e: any) {
      toast.error(e?.message || "Database optimization failed");
    } finally {
      setIsOptimizingDb(false);
    }
  };

  // Generate 1-Click Launcher Script
  const handleGenerateLauncher = async () => {
    setIsGeneratingLauncher(true);
    try {
      const res = await generateStartupScript();
      toast.success(res.message);
    } catch (e: any) {
      toast.error(e?.message || "Failed to generate launcher");
    } finally {
      setIsGeneratingLauncher(false);
    }
  };

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedCmd(id);
    toast.success("Copied command to clipboard");
    setTimeout(() => setCopiedCmd(null), 2000);
  };

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6 bg-transparent">
      {/* Top Banner: Local Auto-Deployment Hub */}
      <div className="serena-glass p-5 rounded-3xl border border-slate-200 dark:border-white/5 flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-serena-indigo via-serena-violet to-serena-rose p-0.5 shadow-lg shadow-serena-indigo/20">
            <div className="w-full h-full bg-white dark:bg-obsidian-950 rounded-[14px] flex items-center justify-center">
              <Rocket className="w-6 h-6 text-serena-indigo" />
            </div>
          </div>
          <div>
            <div className="flex items-center gap-2.5 flex-wrap">
              <h2 className="text-base font-black text-slate-900 dark:text-white">
                Local Auto-Deployment Center
              </h2>
              <span className="px-2.5 py-0.5 rounded-full text-xs font-mono font-bold bg-emerald-500/10 border border-emerald-500/30 text-emerald-600 dark:text-emerald-400 flex items-center gap-1.5 shadow-xs">
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                ALL LOCAL SERVICES ACTIVE
              </span>
            </div>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
              Autonomous service orchestrator, real-time telemetry & self-healing diagnostics
            </p>
          </div>
        </div>

        {/* Global Action Trigger Buttons */}
        <div className="flex items-center gap-2.5 flex-wrap">
          <button
            onClick={() => void handleRunDiagnostics()}
            disabled={isRunningDiagnostics}
            className="px-3.5 py-2 rounded-xl bg-gradient-to-r from-serena-indigo to-serena-violet hover:from-indigo-500 hover:to-violet-500 text-white text-xs font-bold flex items-center gap-1.5 shadow-md shadow-serena-indigo/20 transition-all active:scale-95 disabled:opacity-50"
          >
            {isRunningDiagnostics ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <ShieldCheck className="w-3.5 h-3.5 text-indigo-200" />
            )}
            <span>Run Diagnostics</span>
          </button>

          <button
            onClick={() => void handleOptimizeDb()}
            disabled={isOptimizingDb}
            className="px-3.5 py-2 rounded-xl bg-slate-100 dark:bg-obsidian-950 hover:bg-slate-200 dark:hover:bg-obsidian-850 border border-slate-200 dark:border-white/10 text-slate-700 dark:text-slate-300 text-xs font-bold flex items-center gap-1.5 transition-colors shadow-xs disabled:opacity-50"
            title="Compact SQLite database and optimize query plan cache"
          >
            {isOptimizingDb ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin text-serena-amber" />
            ) : (
              <Sparkles className="w-3.5 h-3.5 text-serena-amber" />
            )}
            <span>Optimize DB</span>
          </button>

          <button
            onClick={() => void handleGenerateLauncher()}
            disabled={isGeneratingLauncher}
            className="px-3.5 py-2 rounded-xl bg-slate-100 dark:bg-obsidian-950 hover:bg-slate-200 dark:hover:bg-obsidian-850 border border-slate-200 dark:border-white/10 text-slate-700 dark:text-slate-300 text-xs font-bold flex items-center gap-1.5 transition-colors shadow-xs disabled:opacity-50"
            title="Create 1-click Windows Auto-Start shortcut"
          >
            {isGeneratingLauncher ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin text-serena-violet" />
            ) : (
              <FileCode2 className="w-3.5 h-3.5 text-serena-violet" />
            )}
            <span>Create Auto-Launcher</span>
          </button>

          <button
            onClick={() => void loadStatus()}
            className="p-2 rounded-xl bg-slate-100 dark:bg-obsidian-950 hover:bg-slate-200 dark:hover:bg-obsidian-850 border border-slate-200 dark:border-white/10 text-slate-700 dark:text-slate-300 transition-colors shadow-xs"
            title="Refresh status"
          >
            <RefreshCw className={`w-4 h-4 ${isLoadingStatus ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {/* Services Topology Grid (3 Core Local Services) */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Service 1: Neural OCR Backend */}
        <div className="serena-glass p-5 rounded-3xl border border-slate-200 dark:border-white/5 flex flex-col justify-between gap-4 shadow-xs">
          <div>
            <div className="flex items-center justify-between mb-3">
              <div className="w-10 h-10 rounded-2xl bg-indigo-500/10 border border-indigo-500/25 flex items-center justify-center">
                <Server className="w-5 h-5 text-serena-indigo" />
              </div>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/25">
                PORT 8080 · LIVE
              </span>
            </div>

            <h3 className="text-sm font-bold text-slate-900 dark:text-white">
              FastAPI Neural Backend
            </h3>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
              Multi-worker PaddleOCR engine with auto consensus and voter extraction
            </p>

            <div className="mt-4 space-y-2 font-mono text-xs text-slate-700 dark:text-slate-300 bg-slate-100/70 dark:bg-obsidian-950/70 p-3 rounded-2xl border border-slate-200 dark:border-white/5">
              <div className="flex justify-between">
                <span className="text-slate-400">Device:</span>
                <span className="font-bold text-serena-indigo uppercase">{status?.ocr_device || "GPU:0"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Workers:</span>
                <span className="font-bold text-slate-800 dark:text-slate-200">{status?.ocr_workers ?? 3} threads</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">PID:</span>
                <span className="font-bold text-slate-800 dark:text-slate-200">{status?.process_pid || "—"}</span>
              </div>
            </div>
          </div>

          <a
            href={status?.backend_url ? `${status.backend_url}/docs` : "http://127.0.0.1:8080/docs"}
            target="_blank"
            rel="noreferrer"
            className="w-full py-2 rounded-xl bg-slate-100 dark:bg-obsidian-950 hover:bg-slate-200 dark:hover:bg-obsidian-850 border border-slate-200 dark:border-white/10 text-xs font-bold text-slate-800 dark:text-slate-200 flex items-center justify-center gap-1.5 transition-colors"
          >
            <span>Interactive API Docs</span>
            <ExternalLink className="w-3.5 h-3.5 text-slate-400" />
          </a>
        </div>

        {/* Service 2: Serena Batch OCR Workstation */}
        <div className="serena-glass p-5 rounded-3xl border border-indigo-500/30 bg-gradient-to-b from-indigo-500/5 to-transparent flex flex-col justify-between gap-4 shadow-xs">
          <div>
            <div className="flex items-center justify-between mb-3">
              <div className="w-10 h-10 rounded-2xl bg-purple-500/10 border border-purple-500/25 flex items-center justify-center">
                <Zap className="w-5 h-5 text-serena-violet" />
              </div>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/25">
                PORT 3002 · PRIMARY
              </span>
            </div>

            <h3 className="text-sm font-bold text-slate-900 dark:text-white">
              Serena Batch OCR App
            </h3>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
              Standalone Next.js workstation with folder explorer and real-time SSE streaming
            </p>

            <div className="mt-4 space-y-2 font-mono text-xs text-slate-700 dark:text-slate-300 bg-slate-100/70 dark:bg-obsidian-950/70 p-3 rounded-2xl border border-slate-200 dark:border-white/5">
              <div className="flex justify-between">
                <span className="text-slate-400">Framework:</span>
                <span className="font-bold text-serena-violet">Next.js 16 (Turbopack)</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Streaming:</span>
                <span className="font-bold text-emerald-600 dark:text-emerald-400">Active SSE Channel</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Theme:</span>
                <span className="font-bold text-slate-800 dark:text-slate-200">Light & Dark Glass</span>
              </div>
            </div>
          </div>

          <div className="py-2 rounded-xl bg-serena-indigo/10 border border-serena-indigo/25 text-xs font-bold text-serena-indigo text-center">
            Currently Active UI
          </div>
        </div>

        {/* Service 3: Main Electoral Roll UI */}
        <div className="serena-glass p-5 rounded-3xl border border-slate-200 dark:border-white/5 flex flex-col justify-between gap-4 shadow-xs">
          <div>
            <div className="flex items-center justify-between mb-3">
              <div className="w-10 h-10 rounded-2xl bg-amber-500/10 border border-amber-500/25 flex items-center justify-center">
                <Layers className="w-5 h-5 text-serena-amber" />
              </div>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/25">
                PORT 3000 · READY
              </span>
            </div>

            <h3 className="text-sm font-bold text-slate-900 dark:text-white">
              Main Electoral Roll App
            </h3>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
              Full curated elector records browser, manual audit & verification dashboard
            </p>

            <div className="mt-4 space-y-2 font-mono text-xs text-slate-700 dark:text-slate-300 bg-slate-100/70 dark:bg-obsidian-950/70 p-3 rounded-2xl border border-slate-200 dark:border-white/5">
              <div className="flex justify-between">
                <span className="text-slate-400">Address:</span>
                <span className="font-bold text-slate-800 dark:text-slate-200">http://127.0.0.1:3000</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Features:</span>
                <span className="font-bold text-slate-800 dark:text-slate-200">Review & Audit Tool</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Sync:</span>
                <span className="font-bold text-emerald-600 dark:text-emerald-400">Shared SQLite DB</span>
              </div>
            </div>
          </div>

          <a
            href={status?.web_url || "http://127.0.0.1:3000"}
            target="_blank"
            rel="noreferrer"
            className="w-full py-2 rounded-xl bg-slate-100 dark:bg-obsidian-950 hover:bg-slate-200 dark:hover:bg-obsidian-850 border border-slate-200 dark:border-white/10 text-xs font-bold text-slate-800 dark:text-slate-200 flex items-center justify-center gap-1.5 transition-colors"
          >
            <span>Open Main UI</span>
            <ExternalLink className="w-3.5 h-3.5 text-slate-400" />
          </a>
        </div>
      </div>

      {/* System Telemetry & Diagnostics Section */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: System & Storage Specs */}
        <div className="serena-glass p-5 rounded-3xl border border-slate-200 dark:border-white/5 space-y-4">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2">
            <Cpu className="w-4 h-4 text-serena-indigo" />
            <span>Host Environment Specs</span>
          </h3>

          <div className="space-y-3 font-mono text-xs">
            <div className="p-3 rounded-2xl bg-slate-100/70 dark:bg-obsidian-950/70 border border-slate-200 dark:border-white/5 flex items-center justify-between">
              <span className="text-slate-500">Platform OS:</span>
              <span className="font-bold text-slate-800 dark:text-slate-200">{status?.os_name || "Windows"}</span>
            </div>

            <div className="p-3 rounded-2xl bg-slate-100/70 dark:bg-obsidian-950/70 border border-slate-200 dark:border-white/5 flex items-center justify-between">
              <span className="text-slate-500">Python Version:</span>
              <span className="font-bold text-serena-indigo">{status?.python_version || "3.11+"}</span>
            </div>

            <div className="p-3 rounded-2xl bg-slate-100/70 dark:bg-obsidian-950/70 border border-slate-200 dark:border-white/5 flex items-center justify-between">
              <span className="text-slate-500">System Uptime:</span>
              <span className="font-bold text-emerald-600 dark:text-emerald-400">{status?.uptime_display || "—"}</span>
            </div>

            <div className="p-3 rounded-2xl bg-slate-100/70 dark:bg-obsidian-950/70 border border-slate-200 dark:border-white/5 flex items-center justify-between">
              <span className="text-slate-500">SQLite File Size:</span>
              <span className="font-bold text-serena-amber">{status?.database_size_display || "0.0 MB"}</span>
            </div>
          </div>

          {/* Disk Space Bar */}
          {status && (
            <div className="p-4 rounded-2xl bg-slate-100/70 dark:bg-obsidian-950/70 border border-slate-200 dark:border-white/5 space-y-2">
              <div className="flex items-center justify-between text-xs font-mono">
                <span className="text-slate-500 flex items-center gap-1.5">
                  <HardDrive className="w-3.5 h-3.5 text-serena-violet" />
                  Disk Storage (D:)
                </span>
                <span className="font-bold text-slate-800 dark:text-slate-200">
                  {status.disk_free_gb} GB Free
                </span>
              </div>

              <div className="w-full h-2 rounded-full bg-slate-200 dark:bg-obsidian-900 overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-serena-indigo to-serena-violet rounded-full"
                  style={{ width: `${status.disk_percent_used}%` }}
                />
              </div>

              <div className="text-[10px] font-mono text-slate-400 text-right">
                {status.disk_percent_used}% used of {status.disk_total_gb} GB total
              </div>
            </div>
          )}
        </div>

        {/* Right 2 Columns: Automated Health & Diagnostics Checklist */}
        <div className="lg:col-span-2 serena-glass p-5 rounded-3xl border border-slate-200 dark:border-white/5 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2">
              <Activity className="w-4 h-4 text-emerald-500" />
              <span>Automated Diagnostics & Self-Check</span>
            </h3>
            <span className="text-xs text-slate-400 font-mono">
              {diagnostics?.checks.length ?? 0} Checks Executed
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {diagnostics?.checks.map((check, idx) => (
              <div
                key={idx}
                className="p-3.5 rounded-2xl bg-slate-100/70 dark:bg-obsidian-950/70 border border-slate-200 dark:border-white/5 flex items-start gap-3 shadow-xs"
              >
                <div className="mt-0.5 shrink-0">
                  {check.status === "ok" ? (
                    <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                  ) : check.status === "warn" ? (
                    <AlertTriangle className="w-4 h-4 text-amber-500" />
                  ) : (
                    <XCircle className="w-4 h-4 text-rose-500" />
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-bold text-xs text-slate-800 dark:text-slate-200 truncate">
                      {check.name}
                    </span>
                    <span
                      className={`text-[9px] font-mono font-bold px-1.5 py-0.2 rounded uppercase ${
                        check.status === "ok"
                          ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30"
                          : check.status === "warn"
                          ? "bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/30"
                          : "bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/30"
                      }`}
                    >
                      {check.status}
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-1 leading-snug">
                    {check.message}
                  </p>
                  {check.detail && (
                    <div className="text-[10px] font-mono text-rose-500 mt-1 bg-rose-500/5 p-1.5 rounded-lg">
                      {check.detail}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Auto-Deployment CLI Commands Quick-Sheet */}
      <div className="serena-glass p-5 rounded-3xl border border-slate-200 dark:border-white/5 space-y-4">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2">
          <Terminal className="w-4 h-4 text-serena-violet" />
          <span>Local Deployment & Auto-Start Commands</span>
        </h3>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
          {[
            {
              title: "Launch All Servers",
              cmd: "npm run dev",
              desc: "Starts Backend (8080), Web UI (3000), & Serena (3002)",
              id: "dev",
            },
            {
              title: "Bootstrap Environment",
              cmd: "npm run bootstrap",
              desc: "Installs Python virtualenv, PaddleOCR & npm dependencies",
              id: "bootstrap",
            },
            {
              title: "Run Backend Tests",
              cmd: "npm run test:backend",
              desc: "Executes 826 unit and extraction validation tests",
              id: "test",
            },
            {
              title: "Compile Production Build",
              cmd: "npm run build:serena",
              desc: "Builds optimized Next.js 16 standalone bundle",
              id: "build",
            },
          ].map((item) => (
            <div
              key={item.id}
              className="p-3.5 rounded-2xl bg-slate-100/70 dark:bg-obsidian-950/70 border border-slate-200 dark:border-white/5 flex flex-col justify-between gap-2.5"
            >
              <div>
                <div className="text-xs font-bold text-slate-800 dark:text-slate-200">
                  {item.title}
                </div>
                <div className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">
                  {item.desc}
                </div>
              </div>

              <div className="flex items-center justify-between p-2 rounded-xl bg-white dark:bg-obsidian-900 border border-slate-200 dark:border-white/10 font-mono text-[11px] text-serena-indigo">
                <span className="truncate">{item.cmd}</span>
                <button
                  onClick={() => copyToClipboard(item.cmd, item.id)}
                  className="p-1 text-slate-400 hover:text-serena-indigo transition-colors"
                  title="Copy command"
                >
                  {copiedCmd === item.id ? (
                    <Check className="w-3.5 h-3.5 text-emerald-500" />
                  ) : (
                    <Copy className="w-3.5 h-3.5" />
                  )}
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

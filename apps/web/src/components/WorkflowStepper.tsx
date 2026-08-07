"use client";

/**
 * Interactive Workflow Stepper Header
 *
 * Provides a logical 4-stage pipeline stepper bar:
 * Stage 1: Ingest & PDF Storage (Documents / table)
 * Stage 2: OCR & Quality Inspection (Page Inspector / Review Queue)
 * Stage 3: Electoral Database (Voters / Polling Stations)
 * Stage 4: Intelligence & AI (Dashboard / Analytics / AI Chatbot)
 */

import React from "react";
import {
  FileText,
  Eye,
  ClipboardCheck,
  Users,
  Building2,
  BarChart3,
  Sparkles,
  ChevronRight,
  ChevronLeft,
  CheckCircle2,
  ArrowRight,
  Layers,
  Zap,
} from "lucide-react";
import { useOcrStore, ViewTab } from "@/store/useOcrStore";

interface StageDef {
  id: number;
  title: string;
  subtitle: string;
  primaryTab: ViewTab;
  tabs: ViewTab[];
  icon: React.ElementType;
}

const STAGES: StageDef[] = [
  {
    id: 1,
    title: "1. PDF Ingestion",
    subtitle: "Upload & File Management",
    primaryTab: "table",
    tabs: ["table"],
    icon: FileText,
  },
  {
    id: 2,
    title: "2. OCR Inspection",
    subtitle: "Page BBox & Review Queue",
    primaryTab: "review",
    tabs: ["page", "review"],
    icon: ClipboardCheck,
  },
  {
    id: 3,
    title: "3. Elector Roll",
    subtitle: "Voter Database & Stations",
    primaryTab: "voters",
    tabs: ["voters", "polling_stations"],
    icon: Users,
  },
  {
    id: 4,
    title: "4. Intelligence & AI",
    subtitle: "Analytics & AI Analyst",
    primaryTab: "dashboard",
    tabs: ["dashboard", "analytics"],
    icon: Sparkles,
  },
];

export const WorkflowStepper: React.FC = () => {
  const { activeTab, setActiveTab, files, recordStats } = useOcrStore();

  const currentStage = STAGES.find((s) => s.tabs.includes(activeTab)) || STAGES[0];
  const docCount = files.length;
  const totalPages = files.reduce((acc, f) => acc + (f.page_count || 0), 0);
  const totalRecords = recordStats?.total || 0;
  const verifiedRecords = recordStats?.reviewed || 0;
  const verifiedPct = totalRecords > 0 ? Math.round((verifiedRecords / totalRecords) * 100) : 0;

  const handleNextStage = () => {
    const nextIdx = currentStage.id; // currentStage.id is 1-indexed, so next is currentStage.id
    if (nextIdx < STAGES.length) {
      setActiveTab(STAGES[nextIdx].primaryTab);
    }
  };

  const handlePrevStage = () => {
    const prevIdx = currentStage.id - 2; // 1-indexed id minus 2
    if (prevIdx >= 0) {
      setActiveTab(STAGES[prevIdx].primaryTab);
    }
  };

  return (
    <div className="w-full bg-slate-900/90 dark:bg-slate-950/90 border-b border-indigo-500/20 backdrop-blur-md px-4 py-2.5 shadow-sm transition-all">
      <div className="flex flex-col md:flex-row items-center justify-between gap-3 max-w-7xl mx-auto">
        {/* Stages Stepper Navigation */}
        <div className="flex items-center gap-1.5 sm:gap-2 overflow-x-auto w-full md:w-auto py-0.5">
          {STAGES.map((stage, idx) => {
            const Icon = stage.icon;
            const isActive = currentStage.id === stage.id;
            const isPassed = currentStage.id > stage.id;

            return (
              <React.Fragment key={stage.id}>
                {idx > 0 && (
                  <ChevronRight className="w-3.5 h-3.5 text-slate-600 dark:text-slate-700 shrink-0" />
                )}
                <button
                  type="button"
                  onClick={() => setActiveTab(stage.primaryTab)}
                  className={`group flex items-center gap-2 px-3 py-1.5 rounded-xl border text-xs font-semibold transition-all shrink-0 ${
                    isActive
                      ? "bg-gradient-to-r from-indigo-600 to-violet-600 text-white border-indigo-400/50 shadow-md shadow-indigo-500/20 ring-2 ring-indigo-500/30"
                      : isPassed
                        ? "bg-slate-800/80 text-emerald-300 border-emerald-500/30 hover:bg-slate-800"
                        : "bg-slate-800/40 text-slate-400 border-slate-700/60 hover:bg-slate-800/80 hover:text-slate-200"
                  }`}
                >
                  <div
                    className={`w-5 h-5 rounded-lg flex items-center justify-center shrink-0 ${
                      isActive
                        ? "bg-white/20 text-white"
                        : isPassed
                          ? "bg-emerald-500/20 text-emerald-400"
                          : "bg-slate-700/60 text-slate-400 group-hover:text-slate-200"
                    }`}
                  >
                    {isPassed ? (
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                    ) : (
                      <Icon className="w-3.5 h-3.5" />
                    )}
                  </div>

                  <div className="text-left leading-none">
                    <div className="font-extrabold tracking-tight">{stage.title}</div>
                    <div
                      className={`text-[9px] font-normal mt-0.5 ${
                        isActive
                          ? "text-indigo-100"
                          : isPassed
                            ? "text-emerald-400/80"
                            : "text-slate-500 group-hover:text-slate-400"
                      }`}
                    >
                      {stage.subtitle}
                    </div>
                  </div>
                </button>
              </React.Fragment>
            );
          })}
        </div>

        {/* Workflow Metric Badges & Stage Controls */}
        <div className="flex items-center gap-2.5 shrink-0 w-full md:w-auto justify-between md:justify-end border-t md:border-t-0 border-slate-800 pt-2 md:pt-0">
          <div className="flex items-center gap-2 text-[10px] font-semibold text-slate-300">
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-slate-800/80 border border-slate-700 text-slate-300">
              <FileText className="w-3 h-3 text-indigo-400" />
              <span>{docCount} Roll{docCount === 1 ? "" : "s"}</span>
            </span>

            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-slate-800/80 border border-slate-700 text-slate-300">
              <Users className="w-3 h-3 text-violet-400" />
              <span>{totalRecords.toLocaleString()} Voters</span>
            </span>

            {totalRecords > 0 && (
              <span className="hidden sm:inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 font-bold">
                <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                <span>{verifiedPct}% Verified</span>
              </span>
            )}
          </div>

          {/* Stepper Stage Buttons */}
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={handlePrevStage}
              disabled={currentStage.id === 1}
              title="Previous Workflow Stage"
              className="p-1.5 rounded-lg bg-slate-800/80 hover:bg-slate-700 disabled:opacity-30 disabled:hover:bg-slate-800/80 text-slate-300 transition-colors border border-slate-700/60"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              onClick={handleNextStage}
              disabled={currentStage.id === STAGES.length}
              title="Next Workflow Stage"
              className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:hover:bg-indigo-600 text-white font-bold text-xs transition-colors shadow-sm"
            >
              <span>Next</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

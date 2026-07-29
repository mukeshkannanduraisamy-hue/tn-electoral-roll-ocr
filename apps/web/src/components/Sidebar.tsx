import React from "react";
import { useOcrStore, ViewTab } from "@/store/useOcrStore";
import {
  LayoutDashboard,
  Users,
  Building2,
  FileText,
  PieChart,
  CheckSquare,
  Settings,
  X,
  ChevronLeft,
  ChevronRight,
  ShieldCheck,
  Zap,
} from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { cn } from "@/lib/utils";

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
}

export function Sidebar({ isOpen, onClose, isCollapsed = false, onToggleCollapse }: SidebarProps) {
  const { activeTab, setActiveTab, files, voters, jobs } = useOcrStore();

  const activeJobsCount = jobs.filter(j => j.status === "running" || j.status === "queued").length;

  const navItems: { id: ViewTab; label: string; icon: React.ReactNode; badge?: string | number }[] = [
    { id: "dashboard", label: "Dashboard", icon: <LayoutDashboard className="w-4 h-4 text-indigo-400" /> },
    { id: "voters", label: "Voter Directory", icon: <Users className="w-4 h-4 text-blue-400" />, badge: voters.length > 0 ? voters.length : undefined },
    { id: "polling_stations", label: "Polling Stations", icon: <Building2 className="w-4 h-4 text-teal-400" /> },
    { id: "table", label: "Documents", icon: <FileText className="w-4 h-4 text-violet-400" />, badge: files.length > 0 ? files.length : undefined },
    { id: "analytics", label: "Analytics & Reports", icon: <PieChart className="w-4 h-4 text-emerald-400" /> },
    { id: "review", label: "Review Queue", icon: <CheckSquare className="w-4 h-4 text-amber-400" /> },
    { id: "settings", label: "System Settings", icon: <Settings className="w-4 h-4 text-slate-400" /> },
  ];

  return (
    <aside
      className={cn(
        "flex flex-col justify-between h-full z-40 transition-all duration-200 select-none shrink-0 bg-[hsl(var(--sidebar-bg))] border-r border-[hsl(var(--sidebar-border))]",
        isCollapsed ? "w-16" : "w-60",
        "fixed inset-y-0 left-0 lg:static lg:translate-x-0",
        isOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
      )}
    >
      {/* Brand Header */}
      <div className="h-14 px-4 border-b border-[hsl(var(--sidebar-border))] flex items-center justify-between">
        <div className="flex items-center gap-3 overflow-hidden">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-white font-bold text-xs shadow-md shadow-indigo-500/25 shrink-0">
            VI
          </div>
          {!isCollapsed && (
            <div className="flex flex-col min-w-0">
              <span className="font-bold text-xs tracking-wider text-slate-100 uppercase truncate">VI-MC Platform</span>
              <span className="text-[10px] text-slate-400 truncate">Electoral OCR Enterprise</span>
            </div>
          )}
        </div>

        {/* Mobile close button */}
        <button
          onClick={onClose}
          className="lg:hidden text-slate-400 hover:text-white p-1 rounded-md"
        >
          <X className="w-5 h-5" />
        </button>

        {/* Collapse toggle button for desktop */}
        {onToggleCollapse && (
          <button
            onClick={onToggleCollapse}
            className="hidden lg:flex text-slate-400 hover:text-white p-1 rounded-md hover:bg-slate-800 transition-colors"
            title={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {isCollapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
          </button>
        )}
      </div>

      {/* Navigation Group */}
      <div className="flex-1 overflow-y-auto px-2 py-4 space-y-6">
        <div>
          {!isCollapsed && (
            <div className="px-3 pb-2 text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
              Workspace Nav
            </div>
          )}
          <nav className="space-y-1">
            {navItems.map((item) => {
              const isActive = activeTab === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => {
                    setActiveTab(item.id);
                    onClose();
                  }}
                  className={cn(
                    "w-full flex items-center gap-3 px-3 py-2 rounded-lg text-xs transition-all text-left font-medium",
                    isActive
                      ? "bg-indigo-500/15 text-indigo-400 font-semibold border-l-2 border-indigo-500"
                      : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60",
                    isCollapsed && "justify-center px-0 py-2.5"
                  )}
                  title={isCollapsed ? item.label : undefined}
                >
                  <span className="shrink-0">{item.icon}</span>
                  {!isCollapsed && (
                    <div className="flex-1 flex items-center justify-between overflow-hidden">
                      <span className="truncate">{item.label}</span>
                      {item.badge !== undefined && (
                        <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300">
                          {item.badge}
                        </span>
                      )}
                    </div>
                  )}
                </button>
              );
            })}
          </nav>
        </div>

        {/* System Jobs Banner */}
        {!isCollapsed && activeJobsCount > 0 && (
          <div className="mx-1 p-3 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-xs space-y-1.5 animate-fade-slide">
            <div className="flex items-center gap-2 text-indigo-400 font-semibold text-xs">
              <Zap className="w-3.5 h-3.5 animate-pulse" />
              <span>{activeJobsCount} Active OCR Jobs</span>
            </div>
            <p className="text-[11px] text-slate-400">Processing voter rolls in background worker pool.</p>
          </div>
        )}
      </div>

      {/* Sidebar Footer */}
      <div className="h-12 px-4 border-t border-[hsl(var(--sidebar-border))] bg-[hsl(var(--sidebar-bg))] flex items-center">
        {!isCollapsed ? (
          <div className="w-full flex items-center justify-between text-xs text-slate-400">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              <span className="text-[11px] font-medium text-slate-300">v2.4 Enterprise</span>
            </div>
            <span className="text-[10px] text-slate-500 font-mono-code">Ctrl+K</span>
          </div>
        ) : (
          <div className="w-full flex justify-center">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
          </div>
        )}
      </div>
    </aside>
  );
}

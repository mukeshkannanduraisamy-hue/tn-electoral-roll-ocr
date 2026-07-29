import React from "react";
import { useOcrStore, ViewTab } from "@/store/useOcrStore";
import {
  LayoutDashboard,
  Users,
  Building2,
  FileText,
  PieChart,
  CheckSquare,
  Activity,
  Settings,
  X,
  ChevronLeft,
  ChevronRight,
  ShieldCheck,
  Zap,
  Sparkles,
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

  const navItems: { id: ViewTab; label: string; icon: React.ReactNode; badge?: string | number; shortcut: string }[] = [
    { id: "dashboard", label: "Dashboard", icon: <LayoutDashboard className="w-4 h-4 text-indigo-400" />, shortcut: "1" },
    { id: "voters", label: "Voter Directory", icon: <Users className="w-4 h-4 text-blue-400" />, badge: voters.length > 0 ? voters.length : undefined, shortcut: "2" },
    { id: "polling_stations", label: "Polling Stations", icon: <Building2 className="w-4 h-4 text-teal-400" />, shortcut: "3" },
    { id: "table", label: "Documents", icon: <FileText className="w-4 h-4 text-violet-400" />, badge: files.length > 0 ? files.length : undefined, shortcut: "4" },
    { id: "analytics", label: "Analytics & Reports", icon: <PieChart className="w-4 h-4 text-emerald-400" />, shortcut: "5" },
    { id: "review", label: "Review Queue", icon: <CheckSquare className="w-4 h-4 text-amber-400" />, shortcut: "6" },
    { id: "settings", label: "System Settings", icon: <Settings className="w-4 h-4 text-slate-400" />, shortcut: "7" },
  ];

  return (
    <aside
      className={cn(
        "vimc-sidebar flex flex-col justify-between h-full z-40 transition-all duration-200 select-none shrink-0",
        isCollapsed ? "w-16" : "w-64",
        "fixed inset-y-0 left-0 lg:static lg:translate-x-0",
        isOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
      )}
    >
      {/* Brand Header */}
      <div className="p-4 border-b border-[hsl(var(--sidebar-border))] flex items-center justify-between">
        <div className="flex items-center gap-3 overflow-hidden">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 via-indigo-600 to-violet-600 flex items-center justify-center text-white font-bold text-sm shadow-md shadow-indigo-500/30 shrink-0">
            VI
          </div>
          {!isCollapsed && (
            <div className="flex flex-col min-w-0">
              <span className="font-bold text-xs tracking-wider text-white uppercase truncate">VI-MC Platform</span>
              <span className="text-[10px] text-muted-foreground truncate">Electoral OCR Enterprise</span>
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
      <div className="flex-1 overflow-y-auto px-2.5 py-4 space-y-6">
        <div>
          {!isCollapsed && (
            <div className="px-3 pb-2 text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
              Workspace
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
                    "vimc-sidebar-item w-full text-left transition-all",
                    isActive && "active font-semibold",
                    isCollapsed && "justify-center px-0 py-2.5"
                  )}
                  title={isCollapsed ? item.label : undefined}
                >
                  <span className="shrink-0">{item.icon}</span>
                  {!isCollapsed && (
                    <div className="flex-1 flex items-center justify-between overflow-hidden">
                      <span className="truncate">{item.label}</span>
                      <div className="flex items-center gap-1.5">
                        {item.badge !== undefined && (
                          <Badge variant="indigo" className="text-[10px] px-1.5 py-0 h-4">
                            {item.badge}
                          </Badge>
                        )}
                        <span className="text-[10px] font-mono-code text-slate-600">{item.shortcut}</span>
                      </div>
                    </div>
                  )}
                </button>
              );
            })}
          </nav>
        </div>

        {/* System Jobs Banner */}
        {!isCollapsed && activeJobsCount > 0 && (
          <div className="mx-1 p-3 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-xs space-y-2 animate-fade-slide">
            <div className="flex items-center gap-2 text-indigo-400 font-semibold">
              <Zap className="w-3.5 h-3.5 animate-pulse" />
              <span>{activeJobsCount} Active OCR Jobs</span>
            </div>
            <p className="text-[11px] text-slate-400">Processing voter rolls in background worker pool.</p>
          </div>
        )}
      </div>

      {/* Sidebar Footer */}
      <div className="p-3 border-t border-[hsl(var(--sidebar-border))] bg-[hsl(var(--sidebar-bg))]">
        {!isCollapsed ? (
          <div className="flex items-center justify-between text-xs text-slate-400">
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
              <span className="text-[11px] font-medium text-slate-300">v2.4 Enterprise</span>
            </div>
            <span className="text-[10px] font-mono-code text-slate-500">Press ?</span>
          </div>
        ) : (
          <div className="flex justify-center">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
          </div>
        )}
      </div>
    </aside>
  );
}

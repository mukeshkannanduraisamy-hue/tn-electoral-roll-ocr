"use client";

import React from "react";
import {
  LayoutDashboard,
  FileText,
  Users,
  BarChart3,
  Settings,
  Search,
  TableProperties,
  Eye,
  ClipboardCheck,
  ChevronRight,
  Building2,
  Zap,
} from "lucide-react";
import { useOcrStore } from "@/store/useOcrStore";

interface NavItem {
  id: string;
  label: string;
  icon: React.ElementType;
  badge?: number | string;
  group?: string;
}

const NAV_ITEMS: NavItem[] = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard, group: "main" },
  { id: "voters", label: "Voters", icon: Users, group: "main" },
  { id: "polling_stations", label: "Polling Stations", icon: Building2, group: "main" },
  { id: "table", label: "Documents", icon: FileText, group: "main" },
  { id: "analytics", label: "Analytics", icon: BarChart3, group: "insights" },
  { id: "page", label: "Page Viewer", icon: Eye, group: "tools" },
  { id: "review", label: "Review Queue", icon: ClipboardCheck, group: "tools" },
  { id: "settings", label: "Settings", icon: Settings, group: "system" },
];

const GROUP_LABELS: Record<string, string> = {
  main: "Intelligence",
  insights: "Insights",
  tools: "Tools",
  system: "System",
};

interface SidebarProps {
  isOpen?: boolean;
  onClose?: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ isOpen = false, onClose }) => {
  const { activeTab, setActiveTab, files } = useOcrStore();

  const voterCount = files.reduce((acc, f) => acc + (f.page_count || 0), 0);
  const docCount = files.length;

  const getBadge = (id: string) => {
    if (id === "table" && docCount > 0) return docCount;
    return undefined;
  };

  const handleNav = (id: string) => {
    setActiveTab(id as any);
    onClose?.();
  };

  const groups = ["main", "insights", "tools", "system"];

  return (
    <aside
      className="vimc-sidebar h-full flex flex-col shrink-0 w-56 lg:w-60 z-40 fixed lg:relative inset-y-0"
      data-drawer={isOpen ? "open" : "closed"}
    >
      {/* Logo / Brand */}
      <div className="flex items-center gap-2.5 px-5 py-4 border-b border-white/5">
        <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center shadow-lg shadow-indigo-500/30">
          <Zap className="w-4 h-4 text-white" fill="white" />
        </div>
        <div>
          <div className="text-sm font-bold text-white tracking-tight leading-none">VI-MC</div>
          <div className="text-[10px] text-white/40 font-medium tracking-wider uppercase leading-none mt-0.5">
            Voter Intelligence
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-3 px-3 space-y-0.5">
        {groups.map((group) => {
          const items = NAV_ITEMS.filter((n) => n.group === group);
          if (items.length === 0) return null;
          return (
            <div key={group} className="mb-3">
              <div className="px-2 py-1.5 text-[10px] font-semibold uppercase tracking-widest text-white/20 mb-1">
                {GROUP_LABELS[group]}
              </div>
              {items.map((item) => {
                const Icon = item.icon;
                const isActive = activeTab === item.id;
                const badge = getBadge(item.id);
                return (
                  <button
                    key={item.id}
                    onClick={() => handleNav(item.id)}
                    className={`vimc-sidebar-item w-full text-left ${isActive ? "active" : ""}`}
                  >
                    <Icon className="w-4 h-4 shrink-0" />
                    <span className="flex-1 truncate">{item.label}</span>
                    {badge !== undefined && (
                      <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-white/10 text-white/60 min-w-[20px] text-center">
                        {badge}
                      </span>
                    )}
                    {isActive && (
                      <ChevronRight className="w-3 h-3 text-indigo-400 shrink-0" />
                    )}
                  </button>
                );
              })}
            </div>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="border-t border-white/5 px-3 py-3">
        <div className="flex items-center gap-2 px-2 py-2 rounded-lg bg-white/5">
          <Building2 className="w-3.5 h-3.5 text-white/30 shrink-0" />
          <div className="min-w-0">
            <div className="text-[10px] text-white/30 font-medium truncate">
              Election Commission
            </div>
            <div className="text-[10px] text-white/20 truncate">
              Tamil Nadu SIR 2026
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
};

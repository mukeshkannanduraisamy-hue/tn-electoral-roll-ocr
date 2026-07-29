import React from "react";
import { useOcrStore } from "@/store/useOcrStore";
import { useTheme } from "next-themes";
import {
  Search,
  Upload,
  Download,
  FileSpreadsheet,
  Sun,
  Moon,
  Zap,
  ChevronRight,
  LogOut,
  Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { NotificationCenter } from "@/components/NotificationCenter";
import { useAuthStore } from "@/store/useAuthStore";

interface NavbarProps {
  onOpenUpload: () => void;
  onOpenExport: () => void;
  onOpenBulkExtract: () => void;
  onOpenCommandPalette?: () => void;
}

export function Navbar({
  onOpenUpload,
  onOpenExport,
  onOpenBulkExtract,
  onOpenCommandPalette,
}: NavbarProps) {
  const { activeTab, jobs } = useOcrStore();
  const { theme, setTheme } = useTheme();
  const { user, signOut, authEnabled } = useAuthStore();

  const isJobRunning = jobs.some((j) => j.status === "running");

  const tabLabels: Record<string, string> = {
    dashboard: "Dashboard Overview",
    voters: "Voter Directory & CRM",
    polling_stations: "Polling Station Analytics",
    table: "Document Manager",
    analytics: "Intelligence & Reports",
    page: "OCR Page Inspector",
    review: "Low-Confidence Verification Queue",
    settings: "System Settings",
  };

  return (
    <header className="glass-header h-14 border-b border-border/80 px-4 flex items-center justify-between shrink-0 select-none">
      {/* Breadcrumb Path */}
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span className="font-bold text-foreground flex items-center gap-1.5">
          <Sparkles className="w-3.5 h-3.5 text-primary" />
          <span>VI-MC Enterprise</span>
        </span>
        <ChevronRight className="w-3.5 h-3.5 text-muted-foreground/50" />
        <span className="font-semibold text-foreground">{tabLabels[activeTab] || "Workspace"}</span>
      </div>

      {/* Global Command Palette Bar Trigger */}
      <div className="hidden md:flex items-center flex-1 max-w-md mx-6">
        <button
          onClick={onOpenCommandPalette}
          className="w-full h-8 px-3 rounded-lg bg-muted/60 hover:bg-muted border border-border/60 text-muted-foreground hover:text-foreground text-xs flex items-center justify-between transition-colors cursor-pointer"
        >
          <div className="flex items-center gap-2">
            <Search className="w-3.5 h-3.5 text-indigo-500" />
            <span>Search voters, EPIC IDs, files...</span>
          </div>
          <span className="font-mono-code text-[10px] px-1.5 py-0.5 rounded bg-background border border-border">
            Ctrl K
          </span>
        </button>
      </div>

      {/* Quick Actions & Controls */}
      <div className="flex items-center gap-2">
        {/* Live Processing Indicator */}
        {isJobRunning && (
          <Badge variant="indigo" className="hidden sm:inline-flex animate-pulse">
            <Zap className="w-3 h-3 text-indigo-500" />
            <span>OCR Active</span>
          </Badge>
        )}

        {/* Action Buttons */}
        <Button
          variant="gradient"
          size="sm"
          onClick={onOpenUpload}
          leftIcon={<Upload className="w-3.5 h-3.5" />}
        >
          <span>Upload PDF</span>
        </Button>

        <Button
          variant="secondary"
          size="sm"
          onClick={onOpenBulkExtract}
          className="hidden sm:inline-flex"
          leftIcon={<FileSpreadsheet className="w-3.5 h-3.5 text-violet-500" />}
        >
          <span>Batch OCR</span>
        </Button>

        <Button
          variant="outline"
          size="sm"
          onClick={onOpenExport}
          className="hidden md:inline-flex"
          leftIcon={<Download className="w-3.5 h-3.5 text-emerald-500" />}
        >
          <span>Export</span>
        </Button>

        {/* Notifications Tray */}
        <NotificationCenter />

        {/* Dark/Light Theme Switcher */}
        <button
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          className="p-2 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
          title={`Switch to ${theme === "dark" ? "Light" : "Dark"} Mode`}
        >
          {theme === "dark" ? <Sun className="w-4 h-4 text-amber-500" /> : <Moon className="w-4 h-4 text-slate-600" />}
        </button>

        {/* User Profile / Auth */}
        {authEnabled && user && (
          <div className="flex items-center gap-2 pl-2 border-l border-border/60">
            <div className="w-7 h-7 rounded-full bg-primary/20 text-primary flex items-center justify-center font-bold text-xs">
              {user.username.substring(0, 2).toUpperCase()}
            </div>
            <button
              onClick={signOut}
              className="p-1.5 rounded-lg text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
              title="Sign Out"
            >
              <LogOut className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
      </div>
    </header>
  );
}

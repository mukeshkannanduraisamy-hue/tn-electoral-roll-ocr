import React, { useState } from "react";
import { Bell, CheckCircle2, AlertTriangle, Info, X, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { cn } from "@/lib/utils";

export interface AppNotification {
  id: string;
  title: string;
  message: string;
  timestamp: string;
  type: "success" | "warning" | "info" | "error";
  read: boolean;
}

export function NotificationCenter() {
  const [isOpen, setIsOpen] = useState(false);
  const [notifications, setNotifications] = useState<AppNotification[]>([
    {
      id: "1",
      title: "OCR Pipeline Initialization",
      message: "PaddleOCR PP-OCRv5 engine loaded with 8 worker threads.",
      timestamp: "Just now",
      type: "success",
      read: false,
    },
    {
      id: "2",
      title: "SQLite Engine Active",
      message: "Database connection pool established with 60s lock timeout.",
      timestamp: "5 min ago",
      type: "info",
      read: false,
    },
    {
      id: "3",
      title: "Review Queue Updated",
      message: "2 voter records flagged for low OCR confidence verification.",
      timestamp: "12 min ago",
      type: "warning",
      read: true,
    },
  ]);

  const unreadCount = notifications.filter((n) => !n.read).length;

  const markAllRead = () => {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
  };

  const clearAll = () => {
    setNotifications([]);
  };

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="relative p-2 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
        aria-label="Notifications"
      >
        <Bell className="w-4 h-4" />
        {unreadCount > 0 && (
          <span className="absolute top-1 right-1 h-2 w-2 rounded-full bg-indigo-500 animate-pulse" />
        )}
      </button>

      {isOpen && (
        <>
          <div
            className="fixed inset-0 z-40"
            onClick={() => setIsOpen(false)}
            aria-hidden="true"
          />
          <div className="absolute right-0 mt-2 w-80 sm:w-96 rounded-xl glass shadow-2xl border border-border z-50 animate-scale-in overflow-hidden">
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-border/60 bg-muted/40">
              <div className="flex items-center gap-2">
                <Bell className="w-4 h-4 text-primary" />
                <span className="text-xs font-semibold text-foreground">Notifications</span>
                {unreadCount > 0 && (
                  <Badge variant="indigo">{unreadCount} new</Badge>
                )}
              </div>
              <div className="flex items-center gap-2 text-xs">
                {unreadCount > 0 && (
                  <button
                    onClick={markAllRead}
                    className="text-muted-foreground hover:text-primary transition-colors text-[11px]"
                  >
                    Mark read
                  </button>
                )}
                {notifications.length > 0 && (
                  <button
                    onClick={clearAll}
                    className="text-muted-foreground hover:text-destructive transition-colors"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            </div>

            {/* List */}
            <div className="max-h-80 overflow-y-auto divide-y divide-border/40">
              {notifications.length === 0 ? (
                <div className="p-6 text-center text-xs text-muted-foreground">
                  No notifications yet.
                </div>
              ) : (
                notifications.map((n) => (
                  <div
                    key={n.id}
                    className={cn(
                      "p-3.5 flex items-start gap-3 transition-colors text-xs hover:bg-muted/40",
                      !n.read && "bg-primary/5"
                    )}
                  >
                    {n.type === "success" && (
                      <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0 mt-0.5" />
                    )}
                    {n.type === "warning" && (
                      <AlertTriangle className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" />
                    )}
                    {n.type === "info" && (
                      <Info className="w-4 h-4 text-sky-500 shrink-0 mt-0.5" />
                    )}
                    {n.type === "error" && (
                      <X className="w-4 h-4 text-rose-500 shrink-0 mt-0.5" />
                    )}
                    <div className="flex-1 space-y-0.5">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-foreground">{n.title}</span>
                        <span className="text-[10px] text-muted-foreground">{n.timestamp}</span>
                      </div>
                      <p className="text-muted-foreground leading-relaxed">{n.message}</p>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

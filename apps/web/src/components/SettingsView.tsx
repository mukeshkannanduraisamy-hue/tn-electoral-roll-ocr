import React, { useState } from "react";
import { Settings, Cpu, Database, Sliders, Shield, Terminal, CheckCircle2, Sparkles } from "lucide-react";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";

export function SettingsView() {
  const [workers, setWorkers] = useState(8);
  const [device, setDevice] = useState("cpu");
  const [saved, setSaved] = useState(false);

  const handleSave = () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 2500);
  };

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6 bg-background animate-fade-slide">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground flex items-center gap-2">
            <Settings className="w-6 h-6 text-slate-400" />
            <span>System Settings</span>
          </h1>
          <p className="text-xs text-muted-foreground">
            Configure OCR engine parameters, database connection pool, and hardware acceleration.
          </p>
        </div>

        <Button
          variant="gradient"
          size="md"
          onClick={handleSave}
          leftIcon={<CheckCircle2 className="w-4 h-4" />}
        >
          {saved ? "Settings Saved!" : "Save Configuration"}
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* OCR Engine Settings */}
        <Card className="p-5 space-y-4">
          <CardHeader className="p-0">
            <CardTitle className="text-sm font-bold flex items-center gap-2">
              <Cpu className="w-4 h-4 text-indigo-500" />
              <span>PaddleOCR Inference Engine</span>
            </CardTitle>
            <CardDescription>Model weights and thread pool sizing</CardDescription>
          </CardHeader>
          <CardContent className="p-0 space-y-4 text-xs">
            <div className="space-y-1.5">
              <label className="font-semibold text-foreground">Worker Thread Pool Count</label>
              <div className="flex items-center gap-3">
                <input
                  type="range"
                  min={1}
                  max={16}
                  value={workers}
                  onChange={(e) => setWorkers(parseInt(e.target.value, 10))}
                  className="flex-1 accent-indigo-500"
                />
                <span className="font-mono-code font-bold text-indigo-400 px-2 py-1 bg-muted rounded">{workers} Threads</span>
              </div>
              <p className="text-[11px] text-muted-foreground">Long-lived worker threads initialized with thread lock.</p>
            </div>

            <div className="space-y-1.5 pt-2">
              <label className="font-semibold text-foreground">Acceleration Device</label>
              <select
                value={device}
                onChange={(e) => setDevice(e.target.value)}
                className="w-full h-9 rounded-lg border border-input bg-background px-3 text-xs"
              >
                <option value="cpu">CPU (MKL / OpenMP Multi-threaded)</option>
                <option value="cuda">NVIDIA CUDA GPU Acceleration</option>
              </select>
            </div>
          </CardContent>
        </Card>

        {/* Database & Pool Tuning */}
        <Card className="p-5 space-y-4">
          <CardHeader className="p-0">
            <CardTitle className="text-sm font-bold flex items-center gap-2">
              <Database className="w-4 h-4 text-emerald-500" />
              <span>SQLite & Storage Engine</span>
            </CardTitle>
            <CardDescription>Lock timeout and WAL journaling</CardDescription>
          </CardHeader>
          <CardContent className="p-0 space-y-3 text-xs">
            <div className="flex items-center justify-between p-2.5 rounded-lg bg-muted/50 border border-border/40">
              <span className="text-muted-foreground">SQLite Busy Timeout</span>
              <Badge variant="emerald">60.0 Seconds</Badge>
            </div>
            <div className="flex items-center justify-between p-2.5 rounded-lg bg-muted/50 border border-border/40">
              <span className="text-muted-foreground">Journal Mode</span>
              <Badge variant="indigo">WAL (Write-Ahead Logging)</Badge>
            </div>
            <div className="flex items-center justify-between p-2.5 rounded-lg bg-muted/50 border border-border/40">
              <span className="text-muted-foreground">Data Storage Path</span>
              <span className="font-mono-code text-[11px]">D:\OCR\data\ocr.db</span>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

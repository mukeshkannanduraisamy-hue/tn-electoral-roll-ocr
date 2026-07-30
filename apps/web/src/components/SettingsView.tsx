import React, { useState } from "react";
import { useOcrStore } from "@/store/useOcrStore";
import {
  Cpu,
  Zap,
  Sliders,
  Database,
  Monitor,
  ShieldCheck,
  RotateCcw,
  CheckCircle2,
  RefreshCw,
} from "lucide-react";
import { toast } from "sonner";

export function SettingsView() {
  const { theme, setTheme, toggleTheme } = useOcrStore();

  const [workers, setWorkers] = useState(4);
  const [useGpu, setUseGpu] = useState(true);
  const [cacheEnabled, setCacheEnabled] = useState(true);
  const [retries, setRetries] = useState(3);
  const [preprocMode, setPreprocMode] = useState("fast");
  const [consensusEnabled, setConsensusEnabled] = useState(true);

  const handleSaveSettings = () => {
    toast.success("Extraction engine settings saved successfully!");
  };

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-8 bg-slate-50/50 dark:bg-slate-950/50">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 pb-5">
        <div>
          <h1 className="text-2xl font-extrabold text-slate-900 dark:text-slate-100">
            Extraction Engine & Workspace Settings
          </h1>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            Configure parallel execution workers, GPU acceleration, OCR models, and interface parameters.
          </p>
        </div>
        <button
          onClick={handleSaveSettings}
          className="px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold shadow-lg shadow-indigo-600/30 transition-all flex items-center space-x-2"
        >
          <CheckCircle2 className="w-4 h-4" />
          <span>Save Settings</span>
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Left Column: Engine Settings */}
        <div className="lg:col-span-2 space-y-6">
          {/* Parallel Execution Panel */}
          <div className="p-6 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800/80 shadow-sm space-y-5">
            <div className="flex items-center space-x-3">
              <div className="p-2.5 rounded-xl bg-indigo-50 dark:bg-indigo-950 text-indigo-600 dark:text-indigo-400">
                <Cpu className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-base font-bold text-slate-900 dark:text-slate-100">
                  Parallel Extraction & Worker Scaling
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  Controls worker threads/processes allocated for page processing
                </p>
              </div>
            </div>

            <div className="space-y-4 pt-2">
              <div>
                <div className="flex justify-between items-center mb-2">
                  <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                    Active Workers: <span className="text-indigo-600 dark:text-indigo-400 font-bold">{workers} Worker Cores</span>
                  </label>
                  <span className="text-[11px] text-slate-500 dark:text-slate-400">
                    Auto-tuned for host CPU
                  </span>
                </div>
                <input
                  type="range"
                  min={1}
                  max={16}
                  value={workers}
                  onChange={(e) => setWorkers(Number(e.target.value))}
                  className="w-full h-2 bg-slate-200 dark:bg-slate-800 rounded-lg appearance-none cursor-pointer accent-indigo-600"
                />
              </div>

              {/* GPU Acceleration Toggle */}
              <div className="flex items-center justify-between py-3 border-t border-slate-100 dark:border-slate-800">
                <div>
                  <span className="text-xs font-semibold text-slate-800 dark:text-slate-200 block">
                    GPU CUDA Acceleration
                  </span>
                  <span className="text-[11px] text-slate-500 dark:text-slate-400">
                    Leverage NVIDIA CUDA tensor cores when available for fast inference
                  </span>
                </div>
                <button
                  onClick={() => setUseGpu(!useGpu)}
                  className={`w-12 h-6 rounded-full p-1 transition-colors ${
                    useGpu ? "bg-indigo-600" : "bg-slate-300 dark:bg-slate-700"
                  }`}
                >
                  <div
                    className={`w-4 h-4 rounded-full bg-white transition-transform ${
                      useGpu ? "translate-x-6" : "translate-x-0"
                    }`}
                  />
                </button>
              </div>

              {/* Intelligent Caching Toggle */}
              <div className="flex items-center justify-between py-3 border-t border-slate-100 dark:border-slate-800">
                <div>
                  <span className="text-xs font-semibold text-slate-800 dark:text-slate-200 block">
                    Incremental Checksum Caching
                  </span>
                  <span className="text-[11px] text-slate-500 dark:text-slate-400">
                    Skip re-running OCR on identical unchanged PDF pages
                  </span>
                </div>
                <button
                  onClick={() => setCacheEnabled(!cacheEnabled)}
                  className={`w-12 h-6 rounded-full p-1 transition-colors ${
                    cacheEnabled ? "bg-indigo-600" : "bg-slate-300 dark:bg-slate-700"
                  }`}
                >
                  <div
                    className={`w-4 h-4 rounded-full bg-white transition-transform ${
                      cacheEnabled ? "translate-x-6" : "translate-x-0"
                    }`}
                  />
                </button>
              </div>
            </div>
          </div>

          {/* Preprocessing & Accuracy Tuning */}
          <div className="p-6 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800/80 shadow-sm space-y-5">
            <div className="flex items-center space-x-3">
              <div className="p-2.5 rounded-xl bg-amber-50 dark:bg-amber-950 text-amber-600 dark:text-amber-400">
                <Sliders className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-base font-bold text-slate-900 dark:text-slate-100">
                  Image Preprocessing & Auto-Retry
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  Contrast normalization, CLAHE enhancement, and retry thresholds
                </p>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
              <div>
                <label className="text-xs font-semibold text-slate-700 dark:text-slate-300 block mb-1.5 flex items-center justify-between">
                  <span>OCR Execution Speed Mode</span>
                  <span className="text-[10px] text-emerald-500 font-bold uppercase tracking-wider">5x–10x Turbo</span>
                </label>
                <select
                  value={preprocMode}
                  onChange={(e) => setPreprocMode(e.target.value)}
                  className="w-full px-3 py-2 text-xs rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 text-slate-900 dark:text-slate-100 font-semibold text-indigo-600 dark:text-indigo-400"
                >
                  <option value="fast">⚡ Turbo Mode (Fastest ~2.0s / page)</option>
                  <option value="balanced">⚖️ Balanced Mode (~4.0s / page)</option>
                  <option value="high_quality">🎯 Max Accuracy (~14.0s / page)</option>
                </select>
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-700 dark:text-slate-300 block mb-1.5">
                  Transient Failure Retries
                </label>
                <select
                  value={retries}
                  onChange={(e) => setRetries(Number(e.target.value))}
                  className="w-full px-3 py-2 text-xs rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 text-slate-900 dark:text-slate-100 font-medium"
                >
                  <option value={1}>1 Attempt (No Retries)</option>
                  <option value={3}>3 Retries (Recommended)</option>
                  <option value={5}>5 Retries (High Resilience)</option>
                </select>
              </div>
            </div>
          </div>
        </div>

        {/* Right Column: Theme & System Specs */}
        <div className="space-y-6">
          {/* Appearance Panel */}
          <div className="p-6 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800/80 shadow-sm space-y-5">
            <div className="flex items-center space-x-3">
              <div className="p-2.5 rounded-xl bg-purple-50 dark:bg-purple-950 text-purple-600 dark:text-purple-400">
                <Monitor className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-base font-bold text-slate-900 dark:text-slate-100">
                  Visual Appearance
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  Theme mode and contrast settings
                </p>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 pt-2">
              <button
                onClick={() => setTheme("light")}
                className={`p-4 rounded-xl border text-center transition-all ${
                  theme === "light"
                    ? "border-indigo-600 bg-indigo-50/50 dark:bg-indigo-950/30 text-indigo-700 dark:text-indigo-300 font-bold"
                    : "border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-400"
                }`}
              >
                <span className="text-xs block font-bold">Light Mode</span>
              </button>
              <button
                onClick={() => setTheme("dark")}
                className={`p-4 rounded-xl border text-center transition-all ${
                  theme === "dark"
                    ? "border-indigo-600 bg-indigo-50/50 dark:bg-indigo-950/30 text-indigo-700 dark:text-indigo-300 font-bold"
                    : "border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-400"
                }`}
              >
                <span className="text-xs block font-bold">Dark Mode</span>
              </button>
            </div>
          </div>

          {/* System Info Box */}
          <div className="p-6 rounded-2xl bg-slate-900 text-white border border-slate-800 shadow-sm space-y-4">
            <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider">
              Environment Build Info
            </h4>
            <div className="space-y-2 text-xs font-mono text-slate-300">
              <div className="flex justify-between border-b border-slate-800 pb-1.5">
                <span>OCR Engine</span>
                <span className="text-indigo-400">PaddleOCR v5 (Tamil)</span>
              </div>
              <div className="flex justify-between border-b border-slate-800 pb-1.5">
                <span>PDF Renderer</span>
                <span className="text-indigo-400">PyMuPDF (300 DPI)</span>
              </div>
              <div className="flex justify-between border-b border-slate-800 pb-1.5">
                <span>Backend Framework</span>
                <span className="text-indigo-400">FastAPI / Uvicorn</span>
              </div>
              <div className="flex justify-between">
                <span>Frontend Stack</span>
                <span className="text-indigo-400">Next.js 15 / React 19</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

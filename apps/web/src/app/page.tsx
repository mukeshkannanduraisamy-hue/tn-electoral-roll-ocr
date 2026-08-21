"use client";

import React, { useEffect } from "react";
import { Folder, ArrowRight, ExternalLink } from "lucide-react";

export default function DummyHome() {
  useEffect(() => {
    // Auto-redirect to Serena Windows 11 Explorer on port 3002
    if (typeof window !== "undefined") {
      const targetUrl = window.location.protocol + "//" + window.location.hostname + ":3002";
      window.location.replace(targetUrl);
    }
  }, []);

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-[#1E1E1E] text-white p-6 font-sans">
      <div className="max-w-md w-full p-8 rounded-2xl bg-[#252525] border border-white/10 shadow-2xl text-center space-y-4">
        <div className="w-16 h-16 rounded-2xl bg-blue-600/10 border border-blue-500/20 flex items-center justify-center mx-auto text-blue-500">
          <Folder className="w-8 h-8" />
        </div>
        <h1 className="text-xl font-bold">Serena Windows 11 Explorer</h1>
        <p className="text-xs text-slate-400">
          Main Electoral UI has been disabled. All operations (File Explorer, Database, Deployment) have been unified into Serena OCR Explorer.
        </p>
        <a
          href="http://127.0.0.1:3002"
          className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#005FB8] hover:bg-[#004E98] font-semibold text-xs text-white transition-all shadow-md"
        >
          <span>Open Serena Explorer (Port 3002)</span>
          <ArrowRight className="w-4 h-4" />
        </a>
      </div>
    </div>
  );
}

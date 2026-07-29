"use client";

import React, { useEffect } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Application error boundary caught:", error);
  }, [error]);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col items-center justify-center p-6 space-y-4">
      <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-full text-red-400">
        <AlertTriangle className="w-8 h-8" />
      </div>
      <div className="text-center max-w-md space-y-2">
        <h2 className="text-lg font-bold text-white">Something went wrong</h2>
        <p className="text-sm text-slate-400">
          {error?.message || "An unexpected error occurred while rendering this page."}
        </p>
      </div>
      <button
        onClick={() => reset()}
        className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-sm font-medium transition-colors cursor-pointer"
      >
        <RefreshCw className="w-4 h-4" /> Try Again
      </button>
    </div>
  );
}

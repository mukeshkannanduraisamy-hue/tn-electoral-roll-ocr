import React from "react";
import Link from "next/link";
import { FileQuestion, Home } from "lucide-react";

export default function NotFound() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col items-center justify-center p-6 space-y-4">
      <div className="p-3 bg-indigo-500/10 border border-indigo-500/20 rounded-full text-indigo-400">
        <FileQuestion className="w-8 h-8" />
      </div>
      <div className="text-center max-w-md space-y-2">
        <h2 className="text-lg font-bold text-white">Page Not Found</h2>
        <p className="text-sm text-slate-400">
          The requested page or route could not be found.
        </p>
      </div>
      <Link
        href="/"
        className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-sm font-medium transition-colors"
      >
        <Home className="w-4 h-4" /> Return Home
      </Link>
    </div>
  );
}

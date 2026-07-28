import React from "react";

interface SkeletonProps {
  className?: string;
  variant?: "text" | "rectangular" | "circular" | "card" | "table" | "dashboard";
}

export function SkeletonLoader({ className = "", variant = "rectangular" }: SkeletonProps) {
  if (variant === "text") {
    return (
      <div className={`h-4 bg-slate-200 dark:bg-slate-800 rounded animate-shimmer ${className}`} />
    );
  }

  if (variant === "circular") {
    return (
      <div
        className={`h-10 w-10 rounded-full bg-slate-200 dark:bg-slate-800 animate-shimmer ${className}`}
      />
    );
  }

  if (variant === "card") {
    return (
      <div
        className={`p-5 rounded-2xl border border-slate-200/80 dark:border-slate-800/80 bg-white/70 dark:bg-slate-900/70 backdrop-blur-md shadow-sm space-y-3 ${className}`}
      >
        <div className="flex items-center justify-between">
          <div className="h-4 w-28 bg-slate-200 dark:bg-slate-800 rounded animate-shimmer" />
          <div className="h-8 w-8 rounded-lg bg-slate-200 dark:bg-slate-800 animate-shimmer" />
        </div>
        <div className="h-8 w-20 bg-slate-200 dark:bg-slate-800 rounded animate-shimmer" />
        <div className="h-3 w-36 bg-slate-200 dark:bg-slate-800 rounded animate-shimmer" />
      </div>
    );
  }

  if (variant === "table") {
    return (
      <div className="w-full space-y-3 p-4">
        <div className="flex items-center justify-between pb-2 border-b border-slate-200 dark:border-slate-800">
          <div className="h-6 w-36 bg-slate-200 dark:bg-slate-800 rounded animate-shimmer" />
          <div className="flex gap-2">
            <div className="h-8 w-24 bg-slate-200 dark:bg-slate-800 rounded-lg animate-shimmer" />
            <div className="h-8 w-24 bg-slate-200 dark:bg-slate-800 rounded-lg animate-shimmer" />
          </div>
        </div>
        {Array.from({ length: 6 }).map((_, i) => (
          <div
            key={i}
            className="flex items-center space-x-4 py-3 border-b border-slate-100 dark:border-slate-800/50"
          >
            <div className="h-4 w-4 bg-slate-200 dark:bg-slate-800 rounded animate-shimmer" />
            <div className="h-4 w-1/6 bg-slate-200 dark:bg-slate-800 rounded animate-shimmer" />
            <div className="h-4 w-1/4 bg-slate-200 dark:bg-slate-800 rounded animate-shimmer" />
            <div className="h-4 w-1/5 bg-slate-200 dark:bg-slate-800 rounded animate-shimmer" />
            <div className="h-4 w-12 bg-slate-200 dark:bg-slate-800 rounded animate-shimmer ml-auto" />
          </div>
        ))}
      </div>
    );
  }

  if (variant === "dashboard") {
    return (
      <div className="p-6 space-y-6 animate-pulse">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
          {Array.from({ length: 4 }).map((_, i) => (
            <SkeletonLoader key={i} variant="card" />
          ))}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 h-72 rounded-2xl bg-white/70 dark:bg-slate-900/70 border border-slate-200 dark:border-slate-800 animate-shimmer" />
          <div className="h-72 rounded-2xl bg-white/70 dark:bg-slate-900/70 border border-slate-200 dark:border-slate-800 animate-shimmer" />
        </div>
      </div>
    );
  }

  return (
    <div
      className={`bg-slate-200 dark:bg-slate-800 rounded-lg animate-shimmer ${className}`}
    />
  );
}

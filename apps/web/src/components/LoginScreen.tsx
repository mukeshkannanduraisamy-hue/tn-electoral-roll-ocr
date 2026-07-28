"use client";

import React, { useEffect, useRef, useState } from "react";
import { AlertCircle, Eye, EyeOff, Loader2, LogIn, ScanText } from "lucide-react";
import { useAuthStore } from "@/store/useAuthStore";

export const LoginScreen: React.FC = () => {
  const { signIn, loggingIn, error, clearError } = useAuthStore();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const usernameRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    usernameRef.current?.focus();
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password) return;
    await signIn(username.trim(), password);
    setPassword("");
  };

  const disabled = loggingIn || !username.trim() || !password;

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950 px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="flex flex-col items-center mb-8">
          <div className="h-12 w-12 rounded-2xl bg-indigo-600 flex items-center justify-center shadow-lg shadow-indigo-600/25">
            <ScanText className="h-6 w-6 text-white" />
          </div>
          <h1 className="mt-4 text-xl font-bold text-slate-900 dark:text-slate-100">
            OCR Workspace
          </h1>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            Tamil Nadu Electoral Roll
          </p>
        </div>

        <form
          onSubmit={submit}
          className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-4"
        >
          <div className="space-y-1.5">
            <label
              htmlFor="username"
              className="text-xs font-semibold text-slate-700 dark:text-slate-300"
            >
              Username
            </label>
            <input
              id="username"
              ref={usernameRef}
              type="text"
              autoComplete="username"
              value={username}
              onChange={(e) => {
                setUsername(e.target.value);
                if (error) clearError();
              }}
              className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 px-3 py-2 text-sm text-slate-900 dark:text-slate-100 outline-none focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-500 transition"
              placeholder="admin"
            />
          </div>

          <div className="space-y-1.5">
            <label
              htmlFor="password"
              className="text-xs font-semibold text-slate-700 dark:text-slate-300"
            >
              Password
            </label>
            <div className="relative">
              <input
                id="password"
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value);
                  if (error) clearError();
                }}
                className="w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 px-3 py-2 pr-10 text-sm text-slate-900 dark:text-slate-100 outline-none focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-500 transition"
                placeholder="••••••••••"
              />
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                aria-label={showPassword ? "Hide password" : "Show password"}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition"
              >
                {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>

          {error && (
            <div
              role="alert"
              className="flex items-start gap-2 rounded-lg bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 px-3 py-2 text-xs text-rose-700 dark:text-rose-300"
            >
              <AlertCircle className="h-4 w-4 shrink-0 mt-px" />
              <span>{error}</span>
            </div>
          )}

          <button
            type="submit"
            disabled={disabled}
            className="w-full rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-semibold py-2.5 flex items-center justify-center gap-2 shadow-sm transition"
          >
            {loggingIn ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Signing in…
              </>
            ) : (
              <>
                <LogIn className="h-4 w-4" />
                Sign in
              </>
            )}
          </button>
        </form>

        <p className="mt-5 text-center text-[11px] leading-relaxed text-slate-400 dark:text-slate-600">
          This workspace holds personal data from electoral rolls.
          <br />
          Sign out when you are finished.
        </p>
      </div>
    </div>
  );
};

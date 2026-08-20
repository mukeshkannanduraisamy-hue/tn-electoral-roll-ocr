"use client";

import React, { useState } from "react";
import { Shield, Lock, User, X, Loader2 } from "lucide-react";
import { useSerenaStore } from "@/store/useSerenaStore";

interface AuthModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const SerenaAuthModal: React.FC<AuthModalProps> = ({ isOpen, onClose }) => {
  const { login } = useSerenaStore();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("Admin@123456");
  const [isLoading, setIsLoading] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    const ok = await login(username, password);
    setIsLoading(false);
    if (ok) onClose();
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-md flex items-center justify-center p-4">
      <div className="w-full max-w-sm serena-glass rounded-3xl p-6 border border-slate-200 dark:border-white/10 shadow-2xl relative bg-white dark:bg-obsidian-900">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 p-1.5 rounded-xl text-slate-400 hover:text-slate-700 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-white/5 transition-colors"
        >
          <X className="w-4 h-4" />
        </button>

        <div className="flex items-center gap-3 mb-5">
          <div className="w-10 h-10 rounded-2xl bg-serena-indigo/15 border border-serena-indigo/30 flex items-center justify-center">
            <Shield className="w-5 h-5 text-serena-indigo" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-900 dark:text-white">Serena Authentication</h3>
            <p className="text-[11px] text-slate-500 dark:text-slate-400">Sign in to trigger batch OCR operations</p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-3.5">
          <div>
            <label className="text-[11px] font-medium text-slate-700 dark:text-slate-300 block mb-1">Username</label>
            <div className="relative">
              <User className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full pl-9 pr-3 py-2 bg-slate-50 dark:bg-obsidian-950 border border-slate-200 dark:border-white/10 rounded-xl text-xs text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-serena-indigo/40"
                required
              />
            </div>
          </div>

          <div>
            <label className="text-[11px] font-medium text-slate-700 dark:text-slate-300 block mb-1">Password</label>
            <div className="relative">
              <Lock className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full pl-9 pr-3 py-2 bg-slate-50 dark:bg-obsidian-950 border border-slate-200 dark:border-white/10 rounded-xl text-xs text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-serena-indigo/40"
                required
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="w-full py-2.5 rounded-xl bg-gradient-to-r from-serena-indigo to-serena-violet hover:from-indigo-500 hover:to-violet-500 text-white text-xs font-bold flex items-center justify-center gap-2 shadow-lg shadow-serena-indigo/25 mt-2 transition-all disabled:opacity-50 active:scale-95"
          >
            {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Shield className="w-4 h-4" />}
            <span>Sign In to Pipeline</span>
          </button>
        </form>
      </div>
    </div>
  );
};

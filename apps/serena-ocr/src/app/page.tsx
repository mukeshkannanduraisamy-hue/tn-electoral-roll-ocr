"use client";

import React, { useEffect, useState } from "react";
import { useSerenaStore } from "@/store/useSerenaStore";
import { Windows11Explorer } from "@/components/Windows11Explorer";
import { SerenaAuthModal } from "@/components/SerenaAuthBar";

export default function SerenaHome() {
  const { checkAuth, loadDbFiles, scanCurrentFolder, setTheme } = useSerenaStore();
  const [isAuthOpen, setIsAuthOpen] = useState(false);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const savedTheme = (localStorage.getItem("serena-theme") as "dark" | "light") || "dark";
      setTheme(savedTheme);
    }
    void checkAuth();
    void loadDbFiles();
    void scanCurrentFolder();
  }, []);

  useEffect(() => {
    const handleUnauthorized = () => setIsAuthOpen(true);
    window.addEventListener("serena:unauthorized", handleUnauthorized);
    return () => window.removeEventListener("serena:unauthorized", handleUnauthorized);
  }, []);

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-[#F3F3F3] dark:bg-[#1E1E1E] text-slate-900 dark:text-slate-100 min-w-0 transition-colors duration-150">
      {/* 100% Exact Windows 11 File Explorer App */}
      <Windows11Explorer onOpenAuth={() => setIsAuthOpen(true)} />

      {/* Auth Modal */}
      <SerenaAuthModal isOpen={isAuthOpen} onClose={() => setIsAuthOpen(false)} />
    </div>
  );
}

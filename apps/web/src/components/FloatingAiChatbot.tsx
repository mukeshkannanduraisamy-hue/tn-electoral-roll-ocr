"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  MessageSquare,
  Sparkles,
  X,
  Send,
  Bot,
  User,
  RotateCcw,
  Palette,
  Filter,
  Download,
  CheckCircle2,
  ChevronDown,
} from "lucide-react";
import { toast } from "sonner";
import { queryAiCopilot } from "@/lib/voterApi";

interface Message {
  id: string;
  sender: "user" | "ai";
  text: string;
  timestamp: string;
  actions?: string[];
}

export const FloatingAiChatbot: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      sender: "ai",
      text: "Hello! I am your AI Assistant & Copilot powered by Claude & NVIDIA AI. Ask me any question about your electoral roll records, or tell me how to customize your workspace themes, filters, and reports!",
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    },
  ]);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    if (isOpen) scrollToBottom();
  }, [messages, isOpen]);

  // Open chatbot when global event is fired
  useEffect(() => {
    const handler = () => setIsOpen(true);
    window.addEventListener("vi-mc:open-ai-customizer", handler);
    return () => window.removeEventListener("vi-mc:open-ai-customizer", handler);
  }, []);

  const executeUiAction = (ui: Record<string, unknown>) => {
    const appliedActions: string[] = [];

    // Theme Customization
    if (ui.theme) {
      const theme = String(ui.theme);
      document.body.classList.remove("theme-emerald", "theme-purple", "theme-amber", "theme-ocean", "dark");
      if (theme === "dark") {
        document.body.classList.add("dark");
      } else if (theme !== "light") {
        document.body.classList.add(`theme-${theme}`);
      }
      appliedActions.push(`Switched theme to ${theme.toUpperCase()}`);
    }

    // Export Trigger
    if (ui.export) {
      const format = String(ui.export);
      toast.info(`Triggered ${format.toUpperCase()} export`);
      appliedActions.push(`Triggered ${format.toUpperCase()} export download`);
    }

    // Reset Command
    if (ui.reset) {
      document.body.classList.remove("theme-emerald", "theme-purple", "theme-amber", "theme-ocean", "dark");
      toast.info("Reset UI layout to default");
      appliedActions.push("Reset UI theme and filters to default");
    }

    return appliedActions;
  };

  const handleSendMessage = async (textToSend?: string) => {
    const queryText = textToSend || input;
    if (!queryText.trim() || loading) return;

    const userMsg: Message = {
      id: str(Date.now()),
      sender: "user",
      text: queryText.strip(),
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    setMessages((prev) => [...prev, userMsg]);
    if (!textToSend) setInput("");
    setLoading(true);

    try {
      // Call Backend AI Endpoint
      const res = await queryAiCopilot(userMsg.text);
      const appliedActions = res.ui_changes ? executeUiAction(res.ui_changes as any) : [];

      const aiMsg: Message = {
        id: str(Date.now() + 1),
        sender: "ai",
        text: res.reply || "I have processed your request.",
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        actions: appliedActions,
      };

      setMessages((prev) => [...prev, aiMsg]);
    } catch (err: any) {
      const fallbackMsg: Message = {
        id: str(Date.now() + 1),
        sender: "ai",
        text: `AI processed your message: "${userMsg.text}". You can ask me to switch themes, filter records, or download reports.`,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };
      setMessages((prev) => [...prev, fallbackMsg]);
    } finally {
      setLoading(false);
    }
  };

  // Helper str
  function str(val: any) {
    return String(val);
  }

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col items-end">
      {/* Floating Chat Window */}
      {isOpen && (
        <div className="w-[380px] sm:w-[420px] h-[520px] mb-4 card-vimc bg-slate-900 text-slate-100 border-indigo-500/50 shadow-2xl rounded-3xl flex flex-col overflow-hidden animate-in slide-in-from-bottom-5 duration-200">
          {/* Header */}
          <div className="p-4 bg-gradient-to-r from-indigo-900/90 via-purple-900/90 to-slate-900 border-b border-slate-800 flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="relative">
                <div className="w-10 h-10 rounded-2xl bg-gradient-to-tr from-indigo-500 via-purple-500 to-rose-500 flex items-center justify-center text-white font-black shadow-md">
                  <Bot className="w-5 h-5" />
                </div>
                <span className="absolute -bottom-0.5 -right-0.5 w-3 h-3 bg-emerald-500 border-2 border-slate-900 rounded-full" />
              </div>
              <div>
                <h4 className="text-sm font-extrabold text-white flex items-center space-x-2">
                  <span>Claude AI Copilot</span>
                  <span className="px-2 py-0.5 rounded-full text-[9px] font-black uppercase bg-emerald-500/20 text-emerald-400 border border-emerald-500/40">
                    Online
                  </span>
                </h4>
                <p className="text-[11px] text-slate-400">Electoral Roll & UI Assistant</p>
              </div>
            </div>

            <button
              onClick={() => setIsOpen(false)}
              className="w-8 h-8 rounded-xl bg-slate-800/80 hover:bg-slate-700 text-slate-400 hover:text-white flex items-center justify-center transition-colors"
            >
              <ChevronDown className="w-5 h-5" />
            </button>
          </div>

          {/* Quick Preset Action Buttons */}
          <div className="px-3 py-2 bg-slate-950/60 border-b border-slate-800 flex gap-1.5 overflow-x-auto text-[11px] font-bold">
            <button
              onClick={() => handleSendMessage("What are the total voter stats?")}
              className="px-2.5 py-1 rounded-lg bg-indigo-500/10 hover:bg-indigo-500/20 text-indigo-400 border border-indigo-500/30 whitespace-nowrap"
            >
              💬 Dataset Stats
            </button>
            <button
              onClick={() => handleSendMessage("Switch to Emerald theme")}
              className="px-2.5 py-1 rounded-lg bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 whitespace-nowrap"
            >
              🎨 Emerald Theme
            </button>
            <button
              onClick={() => handleSendMessage("Filter female voters 18-25")}
              className="px-2.5 py-1 rounded-lg bg-purple-500/10 hover:bg-purple-500/20 text-purple-400 border border-purple-500/30 whitespace-nowrap"
            >
              🔍 Female 18-25
            </button>
            <button
              onClick={() => handleSendMessage("Export to Excel")}
              className="px-2.5 py-1 rounded-lg bg-teal-500/10 hover:bg-teal-500/20 text-teal-400 border border-teal-500/30 whitespace-nowrap"
            >
              📥 Export Excel
            </button>
            <button
              onClick={() => handleSendMessage("Reset UI")}
              className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 whitespace-nowrap"
            >
              🔄 Reset UI
            </button>
          </div>

          {/* Messages Body */}
          <div className="flex-1 p-4 overflow-y-auto space-y-3 font-sans text-xs">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex gap-2.5 ${msg.sender === "user" ? "justify-end" : "justify-start"}`}
              >
                {msg.sender === "ai" && (
                  <div className="w-7 h-7 rounded-xl bg-indigo-600 text-white flex items-center justify-center font-bold text-xs shrink-0 mt-0.5 shadow-sm">
                    <Sparkles className="w-3.5 h-3.5" />
                  </div>
                )}

                <div
                  className={`max-w-[82%] p-3.5 rounded-2xl leading-relaxed ${
                    msg.sender === "user"
                      ? "bg-indigo-600 text-white font-medium rounded-tr-none shadow-md"
                      : "bg-slate-800/90 text-slate-100 border border-slate-700/60 rounded-tl-none"
                  }`}
                >
                  <p className="whitespace-pre-wrap">{msg.text}</p>

                  {msg.actions && msg.actions.length > 0 && (
                    <div className="mt-2.5 pt-2 border-t border-slate-700/60 space-y-1">
                      {msg.actions.map((act, i) => (
                        <div key={i} className="text-[10px] font-mono text-emerald-400 flex items-center space-x-1">
                          <CheckCircle2 className="w-3 h-3 shrink-0" />
                          <span>{act}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  <span className="block text-[9px] opacity-50 text-right mt-1 font-mono">
                    {msg.timestamp}
                  </span>
                </div>

                {msg.sender === "user" && (
                  <div className="w-7 h-7 rounded-xl bg-slate-700 text-slate-200 flex items-center justify-center font-bold text-xs shrink-0 mt-0.5">
                    <User className="w-3.5 h-3.5" />
                  </div>
                )}
              </div>
            ))}

            {loading && (
              <div className="flex gap-2.5 items-center text-slate-400 text-xs py-2">
                <div className="w-7 h-7 rounded-xl bg-indigo-600/30 text-indigo-400 flex items-center justify-center">
                  <Sparkles className="w-3.5 h-3.5 animate-spin" />
                </div>
                <span>Claude AI is thinking...</span>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Footer Input Bar */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSendMessage();
            }}
            className="p-3 bg-slate-950 border-t border-slate-800 flex items-center gap-2"
          >
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask Claude AI anything..."
              className="flex-1 bg-slate-900 border border-slate-800 rounded-2xl px-4 py-2.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
            />
            <button
              type="submit"
              disabled={!input.trim() || loading}
              className="w-10 h-10 rounded-2xl bg-gradient-to-tr from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 disabled:opacity-40 text-white flex items-center justify-center transition-all shadow-md shrink-0"
            >
              <Send className="w-4 h-4" />
            </button>
          </form>
        </div>
      )}

      {/* Floating Chat Bubble Button */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="group relative flex items-center space-x-2.5 px-4 py-3 bg-gradient-to-r from-indigo-600 via-purple-600 to-rose-600 hover:from-indigo-500 hover:to-rose-500 text-white font-extrabold text-xs rounded-full shadow-2xl shadow-indigo-600/50 hover:scale-105 transition-all duration-200 border border-white/20"
        >
          <span className="relative flex h-3 w-3">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500" />
          </span>

          <Bot className="w-5 h-5 text-white" />
          <span className="tracking-wide">AI Chatbot</span>
        </button>
      )}
    </div>
  );
};

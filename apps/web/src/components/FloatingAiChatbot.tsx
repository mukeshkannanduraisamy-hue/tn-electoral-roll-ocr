"use client";

/**
 * The assistant. It answers questions and charts figures; it does not touch the
 * interface.
 *
 * An earlier version applied themes, filters and exports on the model's
 * instruction. That is gone: an assistant that rearranges the workspace while
 * you are reading an electoral roll is doing something you did not ask for, and
 * an operator cannot review a change they did not make. Statistical questions
 * come back as a chart whose numbers were computed by SQL — see
 * `app/services/infographic.py`.
 */

import React, { useState, useEffect, useRef } from "react";
import { Bot, ChevronDown, Send, Sparkles, User } from "lucide-react";
import { queryAiCopilot, getAiSettings } from "@/lib/voterApi";
import { useOcrStore } from "@/store/useOcrStore";
import type { Infographic } from "@ocr/shared-types";
import { InfographicCard } from "./InfographicCard";

interface Message {
  id: string;
  sender: "user" | "ai";
  text: string;
  timestamp: string;
  /** Present when the question was statistical. */
  infographic?: Infographic | null;
}

/** Questions that show what the assistant is for, rather than UI commands. */
const SUGGESTIONS = [
  "Voters by gender",
  "Age profile of the roll",
  "Verification progress",
  "Average age by part",
];

const now = () =>
  new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

let messageCounter = 0;
const nextId = () => `m${++messageCounter}`;

export const FloatingAiChatbot: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  /** Null until the first reply tells us whether a key is configured. */
  const [aiConfigured, setAiConfigured] = useState<boolean | null>(null);
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      sender: "ai",
      text:
        "Ask me about the electoral roll or about using this workspace. " +
        "For figures — counts, averages, breakdowns — I answer with a chart built " +
        "from the database.",
      timestamp: now(),
    },
  ]);

  const { activeTab, activeFileId, activePageId, selectedRecordId, files } = useOcrStore();

  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isOpen) messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isOpen, loading]);

  useEffect(() => {
    if (isOpen && aiConfigured === null) {
      getAiSettings()
        .then((res) => setAiConfigured(res.configured))
        .catch(() => setAiConfigured(false));
    }
  }, [isOpen, aiConfigured]);

  // The navbar button opens the assistant through this event.
  useEffect(() => {
    const handler = () => setIsOpen(true);
    window.addEventListener("vi-mc:open-ai-assistant", handler);
    return () => window.removeEventListener("vi-mc:open-ai-assistant", handler);
  }, []);

  const handleSendMessage = async (textToSend?: string) => {
    const queryText = (textToSend || input).trim();
    if (!queryText || loading) return;

    setMessages((prev) => [
      ...prev,
      { id: nextId(), sender: "user", text: queryText, timestamp: now() },
    ]);
    if (!textToSend) setInput("");
    setLoading(true);

    const activeFileName = files.find((f) => f.id === activeFileId)?.name;

    const context: Record<string, unknown> = {
      activeTab,
      ...(activeFileId ? { activeFileId, activeFileName } : {}),
      ...(activePageId ? { activePageId } : {}),
      ...(selectedRecordId ? { selectedRecordId } : {}),
    };

    try {
      const res = await queryAiCopilot(queryText, context);
      if (typeof res.ai_configured === "boolean") setAiConfigured(res.ai_configured);
      setMessages((prev) => [
        ...prev,
        {
          id: nextId(),
          sender: "ai",
          text: res.reply || "",
          timestamp: now(),
          infographic: res.infographic ?? null,
        },
      ]);
    } catch (err: any) {
      // Say what went wrong. A cheerful "I processed your request" over a failed
      // call teaches an operator to distrust every other answer.
      setMessages((prev) => [
        ...prev,
        {
          id: nextId(),
          sender: "ai",
          text:
            err?.message ||
            "I could not reach the server. Check that the API is running and try again.",
          timestamp: now(),
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col items-end">
      {isOpen && (
        // `dark` is forced: the panel is dark by design, so the chart inside it
        // must use the dark palette even when the rest of the app is light.
        <div className="dark w-[380px] sm:w-[440px] h-[560px] mb-4 bg-slate-900 text-slate-100 border border-indigo-500/50 shadow-2xl rounded-3xl flex flex-col overflow-hidden">
          {/* Header */}
          <div className="p-4 bg-gradient-to-r from-indigo-900/90 via-purple-900/90 to-slate-900 border-b border-slate-800 flex items-center justify-between shrink-0">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-2xl bg-gradient-to-tr from-indigo-500 via-purple-500 to-rose-500 grid place-items-center text-white shadow-md">
                <Bot className="w-5 h-5" />
              </div>
              <div>
                <h4 className="text-sm font-extrabold text-white flex items-center gap-2">
                  <span>AI Assistant</span>
                  {/* Honest status: green only once the server confirms a key. */}
                  {aiConfigured === false ? (
                    <span
                      title="No API key is set. Add one under Settings for full answers."
                      className="px-2 py-0.5 rounded-full text-[9px] font-black uppercase bg-amber-500/20 text-amber-400 border border-amber-500/40"
                    >
                      Offline
                    </span>
                  ) : aiConfigured ? (
                    <span className="px-2 py-0.5 rounded-full text-[9px] font-black uppercase bg-emerald-500/20 text-emerald-400 border border-emerald-500/40">
                      Ready
                    </span>
                  ) : null}
                </h4>
                <p className="text-[11px] text-slate-400">
                  Electoral roll questions &amp; figures
                </p>
              </div>
            </div>

            <button
              onClick={() => setIsOpen(false)}
              aria-label="Close the assistant"
              className="w-8 h-8 rounded-xl bg-slate-800/80 hover:bg-slate-700 text-slate-400 hover:text-white grid place-items-center transition-colors"
            >
              <ChevronDown className="w-5 h-5" />
            </button>
          </div>

          {/* Suggestions */}
          <div className="px-3 py-2 bg-slate-950/60 border-b border-slate-800 flex gap-1.5 overflow-x-auto text-[11px] font-bold shrink-0">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                onClick={() => handleSendMessage(s)}
                disabled={loading}
                className="px-2.5 py-1 rounded-lg bg-indigo-500/10 hover:bg-indigo-500/20 disabled:opacity-40 text-indigo-300 border border-indigo-500/30 whitespace-nowrap transition-colors"
              >
                {s}
              </button>
            ))}
          </div>

          {/* Transcript */}
          <div className="flex-1 p-4 overflow-y-auto space-y-3 text-xs">
            {messages.map((msg) => (
              <div key={msg.id} className="space-y-2">
                <div
                  className={`flex gap-2.5 ${
                    msg.sender === "user" ? "justify-end" : "justify-start"
                  }`}
                >
                  {msg.sender === "ai" && (
                    <div className="w-7 h-7 rounded-xl bg-indigo-600 text-white grid place-items-center shrink-0 mt-0.5 shadow-sm">
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
                    <span className="block text-[9px] opacity-50 text-right mt-1 font-mono">
                      {msg.timestamp}
                    </span>
                  </div>

                  {msg.sender === "user" && (
                    <div className="w-7 h-7 rounded-xl bg-slate-700 text-slate-200 grid place-items-center shrink-0 mt-0.5">
                      <User className="w-3.5 h-3.5" />
                    </div>
                  )}
                </div>

                {/* Full width rather than inside the bubble — a chart squeezed
                    into 82% of a narrow panel stops being readable. */}
                {msg.infographic && <InfographicCard data={msg.infographic} />}
              </div>
            ))}

            {loading && (
              <div className="flex gap-2.5 items-center text-slate-400 py-2">
                <div className="w-7 h-7 rounded-xl bg-indigo-600/30 text-indigo-400 grid place-items-center">
                  <Sparkles className="w-3.5 h-3.5 animate-spin" />
                </div>
                <span>Working…</span>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Composer */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void handleSendMessage();
            }}
            className="p-3 bg-slate-950 border-t border-slate-800 flex items-center gap-2 shrink-0"
          >
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about the roll…"
              aria-label="Message the assistant"
              className="flex-1 bg-slate-900 border border-slate-800 rounded-2xl px-4 py-2.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
            />
            <button
              type="submit"
              disabled={!input.trim() || loading}
              aria-label="Send"
              className="w-10 h-10 rounded-2xl bg-gradient-to-tr from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 disabled:opacity-40 text-white grid place-items-center transition-all shadow-md shrink-0"
            >
              <Send className="w-4 h-4" />
            </button>
          </form>
        </div>
      )}

      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="flex items-center gap-2.5 px-4 py-3 bg-gradient-to-r from-indigo-600 via-purple-600 to-rose-600 hover:from-indigo-500 hover:to-rose-500 text-white font-extrabold text-xs rounded-full shadow-2xl shadow-indigo-600/50 hover:scale-105 transition-all duration-200 border border-white/20"
        >
          <Bot className="w-5 h-5 text-white" />
          <span className="tracking-wide">AI Assistant</span>
        </button>
      )}
    </div>
  );
};

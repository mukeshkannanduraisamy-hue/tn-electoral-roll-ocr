"use client";

/**
 * The assistant.
 *
 * It reads the database and answers; it does not touch the interface. An earlier
 * version applied themes, filters and exports on the model's instruction. That
 * is still gone — the closest this comes is a citation chip, which the operator
 * clicks to open a record. The assistant offers; the operator decides.
 *
 * Every figure shown here came from SQL, and every elector named was returned by
 * a tool. Both are enforced server-side in `services/ai_agent/guards.py`, not
 * requested in a prompt.
 */

import React, { useEffect, useRef, useState } from "react";
import { AlertTriangle, Bot, ChevronDown, Clock, Send, Sparkles, Square, User } from "lucide-react";
import { getAiSettings } from "@/lib/voterApi";
import { useAiChat } from "@/hooks/useAiChat";
import { useOcrStore } from "@/store/useOcrStore";
import { AnswerText, MessageBlocks } from "./ai/MessageBlocks";
import { ThreadMenu } from "./ai/ThreadMenu";
import { ToolTrace } from "./ai/ToolTrace";

/** Questions that show the assistant now reads the database, not just charts it. */
const SUGGESTIONS = [
  "Voters by gender",
  "Which pages failed OCR?",
  "Find electors named Muthu",
  "Records with low confidence",
  "Does part 289's count match the roll?",
];

export const FloatingAiChatbot: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [input, setInput] = useState("");
  const [aiConfigured, setAiConfigured] = useState<boolean | null>(null);

  const {
    messages, threads, threadId, loading, status, steps,
    send, stop, newThread, loadThread, deleteThread, refreshThreads,
  } = useAiChat();

  const { activeTab, activeFileId, activePageId, selectedRecordId, files } = useOcrStore();
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isOpen) endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isOpen, loading, status]);

  useEffect(() => {
    if (isOpen && aiConfigured === null) {
      getAiSettings()
        .then((res) => setAiConfigured(res.configured))
        .catch(() => setAiConfigured(false));
    }
  }, [isOpen, aiConfigured]);

  useEffect(() => {
    const handler = () => setIsOpen(true);
    window.addEventListener("vi-mc:open-ai-assistant", handler);
    return () => window.removeEventListener("vi-mc:open-ai-assistant", handler);
  }, []);

  const submit = (text?: string) => {
    const question = (text ?? input).trim();
    if (!question || loading) return;
    if (!text) setInput("");

    send(question, {
      activeTab,
      ...(activeFileId
        ? { activeFileId, activeFileName: files.find((f) => f.id === activeFileId)?.name }
        : {}),
      ...(activePageId ? { activePageId } : {}),
      ...(selectedRecordId ? { selectedRecordId } : {}),
    });
  };

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col items-end">
      {isOpen && (
        // `dark` is forced: the panel is dark by design, so charts inside it use
        // the dark palette even when the rest of the app is light.
        <div className="dark w-[380px] sm:w-[520px] h-[600px] mb-4 bg-slate-900 text-slate-100 border border-indigo-500/50 shadow-2xl rounded-3xl flex flex-col overflow-hidden">
          <div className="p-4 bg-gradient-to-r from-indigo-900/90 via-purple-900/90 to-slate-900 border-b border-slate-800 flex items-center justify-between shrink-0">
            <div className="flex items-center gap-3 min-w-0">
              <div className="w-10 h-10 rounded-2xl bg-gradient-to-tr from-indigo-500 via-purple-500 to-rose-500 grid place-items-center text-white shadow-md shrink-0">
                <Bot className="w-5 h-5" />
              </div>
              <div className="min-w-0">
                <h4 className="text-sm font-extrabold text-white flex items-center gap-2">
                  <span>AI Analyst</span>
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
                <p className="text-[11px] text-slate-400 truncate">Reads the roll database directly</p>
              </div>
            </div>

            <div className="flex items-center gap-1 shrink-0">
              <ThreadMenu
                threads={threads}
                activeId={threadId}
                onNew={newThread}
                onOpen={(id) => void loadThread(id)}
                onDelete={(id) => void deleteThread(id)}
                onRefresh={() => void refreshThreads()}
              />
              <button
                onClick={() => setIsOpen(false)}
                aria-label="Close the assistant"
                className="w-8 h-8 rounded-xl bg-slate-800/80 hover:bg-slate-700 text-slate-400 hover:text-white grid place-items-center transition-colors"
              >
                <ChevronDown className="w-5 h-5" />
              </button>
            </div>
          </div>

          <div className="px-3 py-2 bg-slate-950/60 border-b border-slate-800 flex gap-1.5 overflow-x-auto text-[11px] font-bold shrink-0">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                onClick={() => submit(s)}
                disabled={loading}
                className="px-2.5 py-1 rounded-lg bg-indigo-500/10 hover:bg-indigo-500/20 disabled:opacity-40 text-indigo-300 border border-indigo-500/30 whitespace-nowrap transition-colors"
              >
                {s}
              </button>
            ))}
          </div>

          <div className="flex-1 p-4 overflow-y-auto space-y-3 text-xs">
            {messages.map((msg) => (
              <div key={msg.id} className="space-y-2">
                <div className={`flex gap-2.5 ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                  {msg.role === "assistant" && (
                    <div className="w-7 h-7 rounded-xl bg-indigo-600 text-white grid place-items-center shrink-0 mt-0.5 shadow-sm">
                      <Sparkles className="w-3.5 h-3.5" />
                    </div>
                  )}

                  <div
                    className={`max-w-[86%] p-3.5 rounded-2xl leading-relaxed ${
                      msg.role === "user"
                        ? "bg-indigo-600 text-white font-medium rounded-tr-none shadow-md"
                        : msg.failed
                          ? "bg-rose-950/40 text-rose-200 border border-rose-800/60 rounded-tl-none"
                          : "bg-slate-800/90 text-slate-100 border border-slate-700/60 rounded-tl-none"
                    }`}
                  >
                    {msg.role === "assistant" ? (
                      <AnswerText text={msg.content} citations={msg.citations} />
                    ) : (
                      <p className="whitespace-pre-wrap">{msg.content}</p>
                    )}
                    {msg.role === "assistant" && msg.provider_notice && (
                      <p className="mt-1.5 flex items-start gap-1 text-[10px] text-amber-400/90">
                        <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" />
                        <span>The provider stopped early: {msg.provider_notice}</span>
                      </p>
                    )}
                    {msg.role === "assistant" && msg.budget_exhausted && (
                      <p className="mt-1.5 flex items-center gap-1 text-[10px] text-slate-500">
                        <Clock className="w-3 h-3 shrink-0" />
                        <span>Ran out of steps before finishing — the answer may be incomplete.</span>
                      </p>
                    )}
                    {msg.role === "assistant" && <ToolTrace steps={msg.tool_trace} />}
                  </div>

                  {msg.role === "user" && (
                    <div className="w-7 h-7 rounded-xl bg-slate-700 text-slate-200 grid place-items-center shrink-0 mt-0.5">
                      <User className="w-3.5 h-3.5" />
                    </div>
                  )}
                </div>

                {/* Full width: a table or chart squeezed into 86% of a narrow
                    panel stops being readable. */}
                {msg.role === "assistant" && <MessageBlocks blocks={msg.blocks} />}
              </div>
            ))}

            {loading && (
              <div className="space-y-1.5">
                <div className="flex gap-2.5 items-center text-slate-400 py-1">
                  <div className="w-7 h-7 rounded-xl bg-indigo-600/30 text-indigo-400 grid place-items-center">
                    <Sparkles className="w-3.5 h-3.5 animate-spin" />
                  </div>
                  <span>{status || "Working"}…</span>
                </div>
                <ToolTrace steps={steps} />
              </div>
            )}
            <div ref={endRef} />
          </div>

          <form
            onSubmit={(e) => { e.preventDefault(); submit(); }}
            className="p-3 bg-slate-950 border-t border-slate-800 flex items-center gap-2 shrink-0"
          >
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about the roll, the records, or the pipeline…"
              aria-label="Message the assistant"
              className="flex-1 bg-slate-900 border border-slate-800 rounded-2xl px-4 py-2.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
            />
            {loading ? (
              <button
                type="button"
                onClick={stop}
                aria-label="Stop"
                className="w-10 h-10 rounded-2xl bg-slate-800 hover:bg-slate-700 text-slate-300 grid place-items-center transition-all shrink-0"
              >
                <Square className="w-3.5 h-3.5" />
              </button>
            ) : (
              <button
                type="submit"
                disabled={!input.trim()}
                aria-label="Send"
                className="w-10 h-10 rounded-2xl bg-gradient-to-tr from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 disabled:opacity-40 text-white grid place-items-center transition-all shadow-md shrink-0"
              >
                <Send className="w-4 h-4" />
              </button>
            )}
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

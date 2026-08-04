"use client";

/**
 * Conversation state for the assistant.
 *
 * The component renders; this decides what a stream of events means. Keeping
 * that split means the panel and any future full-page view show the same
 * conversation without either owning the protocol.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type {
  ChatBlock,
  ChatCitation,
  ChatMessage,
  ChatThreadSummary,
  ChatToolStep,
} from "@ocr/shared-types";
import {
  deleteThread as apiDeleteThread,
  getThread,
  listThreads,
  streamChat,
} from "@/lib/aiChatApi";

let counter = 0;
const nextId = () => `local-${++counter}`;

const WELCOME: ChatMessage = {
  id: "welcome",
  role: "assistant",
  content:
    "Ask me about the electoral roll, the OCR pipeline or this workspace. " +
    "I read the database directly — figures come from SQL, and I show you which " +
    "steps I ran.",
  blocks: [],
  citations: [],
  tool_trace: [],
};

export function useAiChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME]);
  const [threads, setThreads] = useState<ChatThreadSummary[]>([]);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<string>("");
  const [steps, setSteps] = useState<ChatToolStep[]>([]);

  const abortRef = useRef<(() => void) | null>(null);

  const refreshThreads = useCallback(async () => {
    try {
      setThreads((await listThreads()).threads);
    } catch {
      // A missing thread list is not worth interrupting the conversation over.
    }
  }, []);

  useEffect(() => {
    return () => abortRef.current?.();
  }, []);

  const newThread = useCallback(() => {
    abortRef.current?.();
    setThreadId(null);
    setSteps([]);
    setMessages([WELCOME]);
  }, []);

  const loadThread = useCallback(async (id: string) => {
    abortRef.current?.();
    const thread = await getThread(id);
    setThreadId(thread.id);
    setSteps([]);
    setMessages(thread.messages.length ? thread.messages : [WELCOME]);
  }, []);

  const removeThread = useCallback(
    async (id: string) => {
      await apiDeleteThread(id);
      if (id === threadId) newThread();
      void refreshThreads();
    },
    [threadId, newThread, refreshThreads],
  );

  const stop = useCallback(() => {
    abortRef.current?.();
    abortRef.current = null;
    setLoading(false);
    setStatus("");
  }, []);

  const send = useCallback(
    (text: string, context?: Record<string, unknown>) => {
      const question = text.trim();
      if (!question || loading) return;

      const replyId = nextId();
      setMessages((prev) => [
        ...prev,
        { id: nextId(), role: "user", content: question, blocks: [], citations: [], tool_trace: [] },
        { id: replyId, role: "assistant", content: "", blocks: [], citations: [], tool_trace: [], pending: true },
      ]);
      setSteps([]);
      setLoading(true);
      setStatus("Thinking");

      const patch = (change: Partial<ChatMessage>) =>
        setMessages((prev) =>
          prev.map((m) => (m.id === replyId ? { ...m, ...change } : m)),
        );

      abortRef.current = streamChat(
        { message: question, thread_id: threadId, context },
        {
          onEvent: (event) => {
            switch (event.type) {
              case "status":
                if (event.data.thread_id) setThreadId(event.data.thread_id);
                if (event.data.message) setStatus(event.data.message);
                break;
              case "tool_call":
                setStatus(event.data.label);
                break;
              case "tool_result":
                setSteps((prev) => [
                  ...prev,
                  event.data.summary ?? {
                    tool: event.data.name,
                    ok: event.data.ok,
                    error: event.data.error,
                  },
                ]);
                break;
              case "token":
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === replyId ? { ...m, content: m.content + event.data.text } : m,
                  ),
                );
                break;
              case "blocks":
                patch({ blocks: event.data.blocks as ChatBlock[] });
                break;
              case "citations":
                patch({ citations: event.data.citations as ChatCitation[] });
                break;
              case "done":
                patch({
                  content: event.data.content,
                  blocks: event.data.blocks,
                  citations: event.data.citations,
                  tool_trace: event.data.tool_trace,
                  pending: false,
                });
                void refreshThreads();
                break;
              case "error":
                patch({ content: event.data.message, pending: false, failed: true });
                break;
            }
          },
          onError: (message) => patch({ content: message, pending: false, failed: true }),
          onClose: () => {
            setLoading(false);
            setStatus("");
            abortRef.current = null;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === replyId && m.pending
                  ? {
                      ...m,
                      pending: false,
                      failed: !m.content,
                      content: m.content || "The answer was interrupted.",
                    }
                  : m,
              ),
            );
          },
        },
      );
    },
    [loading, threadId, refreshThreads],
  );

  return {
    messages,
    threads,
    threadId,
    loading,
    status,
    steps,
    send,
    stop,
    newThread,
    loadThread,
    deleteThread: removeThread,
    refreshThreads,
  };
}

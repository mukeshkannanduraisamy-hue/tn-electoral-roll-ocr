/**
 * Client for the assistant's streaming endpoint.
 *
 * `EventSource` cannot be used: it is GET-only, and a turn carries the message,
 * the thread and the current view context. So the response body is read as a
 * stream and the SSE frames are parsed here.
 */

import type {
  AgentStreamEvent,
  ChatThread,
  ChatThreadSummary,
} from "@ocr/shared-types";

export interface StreamHandlers {
  onEvent: (event: AgentStreamEvent) => void;
  onClose?: () => void;
  onError?: (message: string) => void;
}

export interface StreamBody {
  message: string;
  thread_id?: string | null;
  context?: Record<string, unknown>;
}

/** Split an SSE buffer into complete frames, keeping the unfinished tail. */
function parseFrames(buffer: string): { events: AgentStreamEvent[]; rest: string } {
  const normalized = buffer.replace(/\r\n/g, "\n");
  const events: AgentStreamEvent[] = [];
  const chunks = normalized.split("\n\n");
  const rest = chunks.pop() ?? "";

  for (const chunk of chunks) {
    let type = "";
    let payload = "";
    for (const line of chunk.split("\n")) {
      if (line.startsWith("event:")) type = line.slice(6).trim();
      else if (line.startsWith("data:")) payload += line.slice(5).trim();
    }
    if (!type || !payload) continue;
    try {
      events.push({ type, data: JSON.parse(payload) } as AgentStreamEvent);
    } catch {
      // A frame we cannot parse is dropped rather than crashing the stream —
      // losing one status line is better than losing the answer.
    }
  }
  return { events, rest };
}

/** Start a turn. Returns a function that aborts it. */
export function streamChat(body: StreamBody, handlers: StreamHandlers): () => void {
  const controller = new AbortController();

  void (async () => {
    try {
      const response = await fetch("/api/ai/chat", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      if (!response.ok || !response.body) {
        handlers.onError?.(
          response.status === 401
            ? "Your session has expired. Sign in again."
            : `The assistant could not be reached (HTTP ${response.status}).`,
        );
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const { events, rest } = parseFrames(buffer);
        buffer = rest;
        for (const event of events) handlers.onEvent(event);
      }
    } catch (err) {
      if ((err as Error)?.name !== "AbortError") {
        handlers.onError?.("The connection to the assistant was lost.");
      }
    } finally {
      handlers.onClose?.();
    }
  })();

  return () => controller.abort();
}

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { credentials: "include", ...init });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

export function listThreads(): Promise<{ threads: ChatThreadSummary[] }> {
  return json("/api/ai/threads");
}

export function getThread(id: string): Promise<ChatThread> {
  return json(`/api/ai/threads/${id}`);
}

export function deleteThread(id: string): Promise<void> {
  return json(`/api/ai/threads/${id}`, { method: "DELETE" });
}

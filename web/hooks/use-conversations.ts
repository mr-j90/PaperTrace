"use client";

import { useCallback, useEffect, useState } from "react";

import { streamChat } from "@/lib/stream";
import type { AssistantMessage, ChatMessage, Conversation } from "@/types/chat";

const STORAGE_KEY = "papertrace.conversations.v1";

/** First user line, trimmed to a sidebar-sized title. */
function titleFrom(question: string): string {
  const line = question.trim().replace(/\s+/g, " ");
  return line.length > 60 ? `${line.slice(0, 60)}…` : line;
}

/** A reload mid-stream leaves `streaming: true` in storage — settle those. */
function settle(conversations: Conversation[]): Conversation[] {
  return conversations.map((c) => ({
    ...c,
    messages: c.messages.map(
      (m): ChatMessage =>
        m.role === "assistant" && m.streaming
          ? { ...m, streaming: false, error: m.text ? undefined : "interrupted — try again" }
          : m,
    ),
  }));
}

/** Conversation list + active thread + the SSE ask loop, persisted to localStorage. */
export function useConversations() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) setConversations(settle(JSON.parse(raw) as Conversation[]));
    } catch {
      // unreadable storage — start fresh
    }
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(conversations));
  }, [conversations, hydrated]);

  const patchConversation = useCallback(
    (id: string, patch: (c: Conversation) => Conversation) => {
      setConversations((all) => all.map((c) => (c.id === id ? patch(c) : c)));
    },
    [],
  );

  const patchLastMessage = useCallback(
    (id: string, patch: (m: AssistantMessage) => AssistantMessage) => {
      patchConversation(id, (c) => {
        const last = c.messages[c.messages.length - 1];
        if (!last || last.role !== "assistant") return c;
        return { ...c, messages: [...c.messages.slice(0, -1), patch(last)] };
      });
    },
    [patchConversation],
  );

  const ask = useCallback(
    async (question: string, model?: string) => {
      const q = question.trim();
      if (!q || busyId) return;

      const pending: ChatMessage[] = [
        { role: "user", text: q },
        { role: "assistant", text: "", citations: [], trace: [], streaming: true },
      ];
      const now = Date.now();

      let id: string;
      if (activeId && conversations.some((c) => c.id === activeId)) {
        id = activeId;
        patchConversation(id, (c) => ({
          ...c,
          updatedAt: now,
          messages: [...c.messages, ...pending],
        }));
      } else {
        id = crypto.randomUUID();
        setConversations((all) => [
          { id, title: titleFrom(q), createdAt: now, updatedAt: now, messages: pending },
          ...all,
        ]);
        setActiveId(id);
      }

      setBusyId(id);
      try {
        for await (const event of streamChat(q, model)) {
          if (event.type === "token") {
            patchLastMessage(id, (m) => ({ ...m, text: m.text + event.text }));
          } else if (event.type === "tool_call") {
            patchLastMessage(id, (m) => ({
              ...m,
              text: "", // pre-tool tokens were loop reasoning, not the answer
              trace: [...m.trace, { name: event.name, args: event.args }],
            }));
          } else if (event.type === "tool_result") {
            patchLastMessage(id, (m) => {
              const trace = [...m.trace];
              const open = trace.findLastIndex((s) => s.name === event.name && !s.summary);
              if (open >= 0)
                trace[open] = { ...trace[open], summary: event.summary, ms: event.ms };
              return { ...m, trace };
            });
          } else if (event.type === "done") {
            patchLastMessage(id, (m) => ({
              ...m,
              text: event.answer,
              citations: event.citations,
              streaming: false,
            }));
          } else if (event.type === "error") {
            patchLastMessage(id, (m) => ({ ...m, streaming: false, error: event.detail }));
          }
        }
      } catch {
        patchLastMessage(id, (m) => ({
          ...m,
          streaming: false,
          error: "connection lost — try again",
        }));
      } finally {
        setBusyId(null);
      }
    },
    [activeId, busyId, conversations, patchConversation, patchLastMessage],
  );

  const newChat = useCallback(() => setActiveId(null), []);

  const deleteChat = useCallback((id: string) => {
    setConversations((all) => all.filter((c) => c.id !== id));
    setActiveId((current) => (current === id ? null : current));
  }, []);

  const renameChat = useCallback(
    (id: string, title: string) => {
      const trimmed = title.trim();
      if (trimmed) patchConversation(id, (c) => ({ ...c, title: trimmed }));
    },
    [patchConversation],
  );

  const setFeedback = useCallback(
    (id: string, index: number, thumbs: "up" | "down") => {
      patchConversation(id, (c) => ({
        ...c,
        messages: c.messages.map((m, i) =>
          i === index && m.role === "assistant" ? { ...m, feedback: thumbs } : m,
        ),
      }));
    },
    [patchConversation],
  );

  return {
    conversations,
    activeId,
    busyId,
    ask,
    newChat,
    selectChat: setActiveId,
    deleteChat,
    renameChat,
    setFeedback,
  };
}

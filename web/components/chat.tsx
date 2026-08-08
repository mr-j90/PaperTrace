"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowUp, ExternalLink, ThumbsDown, ThumbsUp } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Trace } from "@/components/trace";
import { streamChat } from "@/lib/stream";
import { cn } from "@/lib/utils";
import type { AssistantMessage, ChatMessage } from "@/types/chat";

const CHIPS = [
  "How do the main approaches to evaluating RAG faithfulness differ?",
  "How many papers about agent evaluation were published each month of 2026?",
  "What's new in RAG evaluation this month?",
  "What retrieval approaches does the RAG paper by Lewis et al. combine?",
];

function CitationPills({ message }: { message: AssistantMessage }) {
  if (message.citations.length === 0) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {message.citations.map((c) => (
        <a
          key={c.arxiv_id}
          href={c.url}
          target="_blank"
          rel="noreferrer"
          title={c.title}
          className="inline-flex items-center gap-1 rounded-full border border-slate-200 px-2.5 py-0.5 text-xs text-slate-600 hover:border-slate-400 hover:text-slate-900 dark:border-slate-700 dark:text-slate-400 dark:hover:border-slate-500 dark:hover:text-slate-100"
        >
          arxiv:{c.arxiv_id}
          <ExternalLink className="size-3" />
        </a>
      ))}
    </div>
  );
}

function Feedback({
  message,
  question,
  onFeedback,
}: {
  message: AssistantMessage;
  question: string;
  onFeedback: (thumbs: "up" | "down") => void;
}) {
  const [pending, setPending] = useState<"up" | "down" | null>(null);
  const [comment, setComment] = useState("");
  const [failed, setFailed] = useState(false);

  if (message.feedback) {
    return <div className="mt-1.5 text-xs text-slate-400">thanks for the feedback!</div>;
  }

  const send = async () => {
    if (!pending) return;
    const response = await fetch("/api/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        answer: message.text,
        thumbs: pending,
        comment: comment.trim() || null,
      }),
    }).catch(() => null);
    if (response?.ok) {
      onFeedback(pending);
    } else {
      setFailed(true);
    }
  };

  return (
    <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
      {(["up", "down"] as const).map((thumbs) => (
        <button
          key={thumbs}
          type="button"
          aria-label={`thumbs ${thumbs}`}
          onClick={() => setPending(thumbs)}
          className={cn(
            "rounded p-1 text-slate-400 hover:text-slate-700 dark:hover:text-slate-200",
            pending === thumbs && "text-emerald-600 dark:text-emerald-500",
          )}
        >
          {thumbs === "up" ? <ThumbsUp className="size-3.5" /> : <ThumbsDown className="size-3.5" />}
        </button>
      ))}
      {pending && (
        <>
          <input
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void send();
            }}
            placeholder="optional comment…"
            className="w-56 rounded-md border border-slate-200 bg-transparent px-2 py-1 text-xs outline-none focus:border-slate-400 dark:border-slate-700 dark:focus:border-slate-500"
          />
          <button
            type="button"
            onClick={() => void send()}
            className="rounded-md border border-slate-200 px-2 py-1 text-xs text-slate-600 hover:border-slate-400 dark:border-slate-700 dark:text-slate-400"
          >
            send
          </button>
        </>
      )}
      {failed && <span className="text-xs text-amber-600">couldn&apos;t send — try again</span>}
    </div>
  );
}

export function Chat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const patchLast = useCallback((patch: (m: AssistantMessage) => AssistantMessage) => {
    setMessages((all) => {
      const last = all[all.length - 1];
      if (!last || last.role !== "assistant") return all;
      return [...all.slice(0, -1), patch(last)];
    });
  }, []);

  const ask = useCallback(
    async (question: string) => {
      if (!question.trim() || busy) return;
      setBusy(true);
      setInput("");
      setMessages((all) => [
        ...all,
        { role: "user", text: question },
        { role: "assistant", text: "", citations: [], trace: [], streaming: true },
      ]);
      try {
        for await (const event of streamChat(question)) {
          if (event.type === "token") {
            patchLast((m) => ({ ...m, text: m.text + event.text }));
          } else if (event.type === "tool_call") {
            patchLast((m) => ({
              ...m,
              text: "", // pre-tool tokens were loop reasoning, not the answer
              trace: [...m.trace, { name: event.name, args: event.args }],
            }));
          } else if (event.type === "tool_result") {
            patchLast((m) => {
              const trace = [...m.trace];
              const open = trace.findLastIndex((s) => s.name === event.name && !s.summary);
              if (open >= 0)
                trace[open] = { ...trace[open], summary: event.summary, ms: event.ms };
              return { ...m, trace };
            });
          } else if (event.type === "done") {
            patchLast((m) => ({
              ...m,
              text: event.answer,
              citations: event.citations,
              streaming: false,
            }));
          } else if (event.type === "error") {
            patchLast((m) => ({ ...m, streaming: false, error: event.detail }));
          }
        }
      } catch {
        patchLast((m) => ({ ...m, streaming: false, error: "connection lost — try again" }));
      } finally {
        setBusy(false);
      }
    },
    [busy, patchLast],
  );

  const lastQuestionFor = (index: number): string => {
    for (let i = index; i >= 0; i--) {
      const m = messages[i];
      if (m.role === "user") return m.text;
    }
    return "";
  };

  return (
    <div className="mx-auto flex h-dvh max-w-3xl flex-col px-4">
      <header className="flex items-center gap-2 py-4">
        <span className="text-lg font-semibold tracking-tight">PaperTrace</span>
        <span className="text-xs text-slate-400">
          agentic RAG over the RAG / agents / eval / LLMOps literature
        </span>
      </header>

      <main className="flex-1 space-y-6 overflow-y-auto pb-4">
        {messages.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center gap-3">
            <p className="text-sm text-slate-500">Ask about the literature — or try one of these:</p>
            <div className="flex max-w-xl flex-wrap justify-center gap-2">
              {CHIPS.map((chip) => (
                <button
                  key={chip}
                  type="button"
                  onClick={() => {
                    setInput(chip); // populate, then submit
                    void ask(chip);
                  }}
                  className="rounded-full border border-slate-200 px-3 py-1.5 text-left text-xs text-slate-600 hover:border-slate-400 hover:text-slate-900 dark:border-slate-700 dark:text-slate-400 dark:hover:border-slate-500 dark:hover:text-slate-100"
                >
                  {chip}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((message, index) =>
          message.role === "user" ? (
            <div key={index} className="flex justify-end">
              <div className="max-w-[85%] rounded-2xl bg-slate-900 px-4 py-2 text-sm text-slate-50 dark:bg-slate-100 dark:text-slate-900">
                {message.text}
              </div>
            </div>
          ) : (
            <div key={index} className="text-sm">
              <Trace steps={message.trace} streaming={message.streaming} />
              {message.error ? (
                <p className="text-amber-600 dark:text-amber-500">{message.error}</p>
              ) : (
                <div className="prose prose-sm prose-slate max-w-none dark:prose-invert [&_a]:break-all">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {message.text || (message.streaming ? "…" : "")}
                  </ReactMarkdown>
                </div>
              )}
              <CitationPills message={message} />
              {!message.streaming && !message.error && message.text && (
                <Feedback
                  message={message}
                  question={lastQuestionFor(index)}
                  onFeedback={(thumbs) => setFeedbackAt(setMessages, index, thumbs)}
                />
              )}
            </div>
          ),
        )}
        <div ref={bottomRef} />
      </main>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          void ask(input);
        }}
        className="sticky bottom-0 bg-white pb-4 pt-2 dark:bg-slate-950"
      >
        <div className="flex items-end gap-2 rounded-2xl border border-slate-200 p-2 focus-within:border-slate-400 dark:border-slate-700 dark:focus-within:border-slate-500">
          <textarea
            value={input}
            rows={1}
            placeholder="Ask about RAG, agents, evals, LLMOps papers…"
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void ask(input);
              }
            }}
            className="max-h-40 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm outline-none"
          />
          <button
            type="submit"
            disabled={busy || !input.trim()}
            aria-label="send"
            className="rounded-xl bg-slate-900 p-2 text-white disabled:opacity-30 dark:bg-slate-100 dark:text-slate-900"
          >
            <ArrowUp className="size-4" />
          </button>
        </div>
      </form>
    </div>
  );
}

/** Mark feedback on the assistant message at `index`. */
function setFeedbackAt(
  setMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>,
  index: number,
  thumbs: "up" | "down",
) {
  setMessages((all) =>
    all.map((m, i) => (i === index && m.role === "assistant" ? { ...m, feedback: thumbs } : m)),
  );
}

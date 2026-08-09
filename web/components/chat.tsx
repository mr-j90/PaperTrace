"use client";

import { useEffect, useRef, useState } from "react";
import { Aperture, ExternalLink, ThumbsDown, ThumbsUp } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Composer } from "@/components/composer";
import { Trace } from "@/components/trace";
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
        turn_id: message.turnId ?? null,
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

export function Chat({
  messages,
  busy,
  onAsk,
  onFeedback,
  modelId,
  onModelChange,
}: {
  messages: ChatMessage[];
  busy: boolean;
  onAsk: (question: string) => void;
  onFeedback: (index: number, thumbs: "up" | "down") => void;
  modelId: string;
  onModelChange: (id: string) => void;
}) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const lastQuestionFor = (index: number): string => {
    for (let i = index; i >= 0; i--) {
      const m = messages[i];
      if (m.role === "user") return m.text;
    }
    return "";
  };

  if (messages.length === 0) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center px-4 pb-16">
        <div className="w-full max-w-2xl space-y-6">
          <h1 className="flex items-center justify-center gap-3 text-3xl font-semibold tracking-tight md:text-4xl">
            <Aperture className="size-8 text-slate-700 md:size-9 dark:text-slate-300" />
            Let&apos;s dig in.
          </h1>
          <Composer
            busy={busy}
            onAsk={onAsk}
            modelId={modelId}
            onModelChange={onModelChange}
            autoFocus
          />
          <div className="flex flex-wrap justify-center gap-2">
            {CHIPS.map((chip) => (
              <button
                key={chip}
                type="button"
                onClick={() => onAsk(chip)}
                className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-left text-xs text-slate-600 shadow-sm hover:border-slate-300 hover:text-slate-900 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400 dark:hover:border-slate-500 dark:hover:text-slate-100"
              >
                {chip}
              </button>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl space-y-6 px-4 py-6">
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
                    onFeedback={(thumbs) => onFeedback(index, thumbs)}
                  />
                )}
              </div>
            ),
          )}
          <div ref={bottomRef} />
        </div>
      </main>
      <div className="mx-auto w-full max-w-3xl px-4 pb-4">
        <Composer busy={busy} onAsk={onAsk} modelId={modelId} onModelChange={onModelChange} />
      </div>
    </div>
  );
}

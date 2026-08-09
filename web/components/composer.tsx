"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowUp, Check, ChevronDown, Sparkles } from "lucide-react";

import { MODELS } from "@/lib/models";
import { cn } from "@/lib/utils";

function ModelPicker({
  modelId,
  onModelChange,
}: {
  modelId: string;
  onModelChange: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const selected = MODELS.find((m) => m.id === modelId) ?? MODELS[0];

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs text-slate-500 hover:bg-slate-100 hover:text-slate-700 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200"
      >
        <Sparkles className="size-3.5" />
        {selected.label}
        <ChevronDown className={cn("size-3 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="absolute bottom-full left-0 z-50 mb-1.5 w-44 rounded-lg border border-slate-200 bg-white p-1 text-xs shadow-lg dark:border-slate-700 dark:bg-slate-900">
          {MODELS.map((m) => (
            <button
              key={m.id}
              type="button"
              onClick={() => {
                onModelChange(m.id);
                setOpen(false);
              }}
              className="flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
            >
              {m.label}
              {m.id === selected.id && <Check className="size-3.5 text-slate-500" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/** The chat input card: textarea on top, model picker + round send button below. */
export function Composer({
  busy,
  onAsk,
  modelId,
  onModelChange,
  autoFocus = false,
}: {
  busy: boolean;
  onAsk: (question: string) => void;
  modelId: string;
  onModelChange: (id: string) => void;
  autoFocus?: boolean;
}) {
  const [input, setInput] = useState("");

  const submit = () => {
    if (!input.trim() || busy) return;
    onAsk(input);
    setInput("");
  };

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
      className="w-full"
    >
      <div className="rounded-2xl border border-slate-200 bg-white shadow-sm focus-within:border-slate-300 dark:border-slate-700 dark:bg-slate-900 dark:focus-within:border-slate-500">
        <textarea
          value={input}
          rows={2}
          autoFocus={autoFocus}
          placeholder="Ask anything"
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          className="max-h-40 w-full resize-none bg-transparent px-4 pt-3.5 text-sm outline-none placeholder:text-slate-400"
        />
        <div className="flex items-center justify-between px-2.5 pb-2.5 pt-1">
          <ModelPicker modelId={modelId} onModelChange={onModelChange} />
          <button
            type="submit"
            disabled={busy || !input.trim()}
            aria-label="send"
            className="flex size-8 items-center justify-center rounded-full bg-slate-900 text-white transition-colors disabled:bg-slate-300 dark:bg-slate-100 dark:text-slate-900 dark:disabled:bg-slate-700"
          >
            <ArrowUp className="size-4" />
          </button>
        </div>
      </div>
    </form>
  );
}

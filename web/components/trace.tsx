"use client";

import { useState } from "react";
import { ChevronRight, Database, Search } from "lucide-react";

import { cn } from "@/lib/utils";
import type { TraceStep } from "@/types/chat";

function StepIcon({ name }: { name: string }) {
  return name === "metadata_query" ? (
    <Database className="size-3.5 shrink-0" />
  ) : (
    <Search className="size-3.5 shrink-0" />
  );
}

function describeArgs(args: Record<string, unknown>): string {
  const parts = Object.entries(args)
    .filter(([, v]) => v !== null && v !== undefined && v !== "")
    .map(([k, v]) => (k === "query" ? `“${String(v)}”` : `${k}=${String(v)}`));
  return parts.join(" · ");
}

function StepBody({ step }: { step: TraceStep }) {
  const summary = step.summary;
  if (!summary) return <span className="italic text-slate-400 dark:text-slate-500">running…</span>;
  return (
    <div className="space-y-1">
      {summary.sql && (
        <code className="block overflow-x-auto rounded bg-slate-100 px-2 py-1 text-[11px] dark:bg-slate-800">
          {summary.sql}
        </code>
      )}
      {typeof summary.total === "number" && (
        <div className="text-slate-500 dark:text-slate-400">
          {summary.total} matching paper{summary.total === 1 ? "" : "s"}
        </div>
      )}
      {summary.groups && (
        <div className="text-slate-500 dark:text-slate-400">
          {summary.groups.map((g) => `${g.grp}: ${g.n}`).join(" · ")}
        </div>
      )}
      {summary.evidence && summary.evidence.length > 0 && (
        <ul className="space-y-0.5">
          {summary.evidence.map(
            (e, i) =>
              e.arxiv_id && (
                <li key={`${e.arxiv_id}-${i}`} className="truncate text-slate-500 dark:text-slate-400">
                  <span className="font-mono text-[11px]">{e.arxiv_id}</span> {e.title}
                </li>
              ),
          )}
        </ul>
      )}
      {summary.note && <div className="text-amber-600 dark:text-amber-500">{summary.note}</div>}
    </div>
  );
}

/** The inline Trace: streams open while the agent works, collapses per message after. */
export function Trace({ steps, streaming }: { steps: TraceStep[]; streaming: boolean }) {
  const [open, setOpen] = useState<boolean | null>(null); // null = follow streaming state
  const expanded = open ?? streaming;
  if (steps.length === 0) return null;

  return (
    <div className="mb-2 rounded-lg border border-slate-200 text-xs dark:border-slate-800">
      <button
        type="button"
        onClick={() => setOpen(!expanded)}
        className="flex w-full items-center gap-1.5 px-3 py-2 text-left text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
      >
        <ChevronRight className={cn("size-3.5 transition-transform", expanded && "rotate-90")} />
        {streaming ? (
          <span className="animate-pulse">
            thinking — step {steps.length}: {steps[steps.length - 1].name}
          </span>
        ) : (
          <span>
            trace · {steps.length} step{steps.length === 1 ? "" : "s"}
          </span>
        )}
      </button>
      {expanded && (
        <ol className="space-y-2 border-t border-slate-200 px-3 py-2 dark:border-slate-800">
          {steps.map((step, i) => (
            <li key={i} className="space-y-1">
              <div className="flex items-center gap-1.5 font-medium text-slate-700 dark:text-slate-300">
                <StepIcon name={step.name} />
                {step.name}
                <span className="font-normal text-slate-500 dark:text-slate-400">
                  {describeArgs(step.args)}
                </span>
                {typeof step.ms === "number" && (
                  <span className="ml-auto font-normal text-slate-400 dark:text-slate-500">
                    {step.ms} ms
                  </span>
                )}
              </div>
              <div className="pl-5">
                <StepBody step={step} />
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

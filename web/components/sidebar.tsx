"use client";

import { useEffect, useRef, useState } from "react";
import { MessagesSquare, MoreHorizontal, Pencil, Plus, Trash2 } from "lucide-react";

import { cn } from "@/lib/utils";
import type { Conversation } from "@/types/chat";

const RECENTS = 8;

function Row({
  conversation,
  active,
  onSelect,
  onRename,
  onDelete,
}: {
  conversation: Conversation;
  active: boolean;
  onSelect: () => void;
  onRename: (title: string) => void;
  onDelete: () => void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(conversation.title);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const close = (e: MouseEvent) => {
      if (!menuRef.current?.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [menuOpen]);

  const commit = () => {
    setEditing(false);
    onRename(draft);
  };

  if (editing) {
    return (
      <input
        autoFocus
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") commit();
          if (e.key === "Escape") {
            setDraft(conversation.title);
            setEditing(false);
          }
        }}
        className="w-full rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-sm outline-none dark:border-slate-600 dark:bg-slate-900"
      />
    );
  }

  return (
    <div className="group relative">
      <button
        type="button"
        onClick={onSelect}
        className={cn(
          "w-full truncate rounded-lg px-2.5 py-1.5 pr-8 text-left text-sm text-slate-700 hover:bg-slate-200/60 dark:text-slate-300 dark:hover:bg-slate-800",
          active && "bg-slate-200/60 font-medium text-slate-900 dark:bg-slate-800 dark:text-slate-100",
        )}
      >
        {conversation.title}
      </button>
      <button
        type="button"
        aria-label="chat options"
        onClick={() => setMenuOpen((v) => !v)}
        className={cn(
          "absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-1 text-slate-400 opacity-0 hover:text-slate-700 group-hover:opacity-100 dark:hover:text-slate-200",
          (menuOpen || active) && "opacity-100",
        )}
      >
        <MoreHorizontal className="size-4" />
      </button>
      {menuOpen && (
        <div
          ref={menuRef}
          className="absolute right-0 top-9 z-50 w-36 rounded-lg border border-slate-200 bg-white p-1 text-sm shadow-lg dark:border-slate-700 dark:bg-slate-900"
        >
          <button
            type="button"
            onClick={() => {
              setMenuOpen(false);
              setDraft(conversation.title);
              setEditing(true);
            }}
            className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            <Pencil className="size-3.5" /> Rename
          </button>
          <button
            type="button"
            onClick={() => {
              setMenuOpen(false);
              onDelete();
            }}
            className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/50"
          >
            <Trash2 className="size-3.5" /> Delete
          </button>
        </div>
      )}
    </div>
  );
}

export function Sidebar({
  conversations,
  activeId,
  onNew,
  onSelect,
  onRename,
  onDelete,
}: {
  conversations: Conversation[];
  activeId: string | null;
  onNew: () => void;
  onSelect: (id: string) => void;
  onRename: (id: string, title: string) => void;
  onDelete: (id: string) => void;
}) {
  const [showAll, setShowAll] = useState(false);
  const sorted = [...conversations].sort((a, b) => b.updatedAt - a.updatedAt);
  const visible = showAll ? sorted : sorted.slice(0, RECENTS);

  return (
    <div className="flex h-full flex-col">
      <div className="px-4 pb-2 pt-4">
        <div className="text-base font-semibold tracking-tight">PaperTrace</div>
        <div className="text-xs text-slate-400">RAG over AI Engineering &amp; LLMOps literature</div>
      </div>

      <div className="flex items-center justify-between px-4 pb-1 pt-3">
        <span className="text-xs font-medium text-slate-400">Recents</span>
        <button
          type="button"
          aria-label="new chat"
          onClick={onNew}
          className="rounded-md p-1 text-slate-500 hover:bg-slate-200/60 hover:text-slate-900 dark:hover:bg-slate-800 dark:hover:text-slate-100"
        >
          <Plus className="size-4" />
        </button>
      </div>

      <nav className="flex-1 space-y-0.5 overflow-y-auto px-2 pb-2">
        {sorted.length === 0 && (
          <p className="px-2.5 py-1.5 text-xs text-slate-400">no chats yet</p>
        )}
        {visible.map((c) => (
          <Row
            key={c.id}
            conversation={c}
            active={c.id === activeId}
            onSelect={() => onSelect(c.id)}
            onRename={(title) => onRename(c.id, title)}
            onDelete={() => onDelete(c.id)}
          />
        ))}
        <button
          type="button"
          onClick={() => setShowAll((v) => !v)}
          className={cn(
            "flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-sm text-slate-700 hover:bg-slate-200/60 dark:text-slate-300 dark:hover:bg-slate-800",
            showAll && "bg-slate-200/60 dark:bg-slate-800",
          )}
        >
          <MessagesSquare className="size-4" />
          All chats
        </button>
      </nav>
    </div>
  );
}

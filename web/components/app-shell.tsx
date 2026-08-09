"use client";

import { useEffect, useState } from "react";
import { PanelLeft, Plus } from "lucide-react";

import { Chat } from "@/components/chat";
import { Sidebar } from "@/components/sidebar";
import { useConversations } from "@/hooks/use-conversations";
import { DEFAULT_MODEL_ID, MODELS } from "@/lib/models";

const isDesktop = () => window.matchMedia("(min-width: 768px)").matches;
const MODEL_STORAGE_KEY = "papertrace.model";

export function AppShell() {
  const {
    conversations,
    activeId,
    busyId,
    ask,
    newChat,
    selectChat,
    deleteChat,
    renameChat,
    setFeedback,
  } = useConversations();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [modelId, setModelId] = useState(DEFAULT_MODEL_ID);

  useEffect(() => {
    if (isDesktop()) setSidebarOpen(true);
    const saved = localStorage.getItem(MODEL_STORAGE_KEY);
    if (saved && MODELS.some((m) => m.id === saved)) setModelId(saved);
  }, []);

  const selectModel = (id: string) => {
    setModelId(id);
    localStorage.setItem(MODEL_STORAGE_KEY, id);
  };

  const active = conversations.find((c) => c.id === activeId);

  const closeOnMobile = () => {
    if (!isDesktop()) setSidebarOpen(false);
  };

  return (
    <div className="flex h-dvh overflow-hidden">
      {sidebarOpen && (
        <>
          <div
            className="fixed inset-0 z-30 bg-black/20 md:hidden"
            onClick={() => setSidebarOpen(false)}
          />
          <aside className="fixed inset-y-0 left-0 z-40 w-72 shrink-0 border-r border-slate-200 bg-slate-50 md:static md:z-auto dark:border-slate-800 dark:bg-slate-900">
            <Sidebar
              conversations={conversations}
              activeId={activeId}
              onNew={() => {
                newChat();
                closeOnMobile();
              }}
              onSelect={(id) => {
                selectChat(id);
                closeOnMobile();
              }}
              onRename={renameChat}
              onDelete={deleteChat}
            />
          </aside>
        </>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-12 shrink-0 items-center gap-2 border-b border-slate-100 px-3 dark:border-slate-800/60">
          <button
            type="button"
            aria-label="toggle sidebar"
            onClick={() => setSidebarOpen((v) => !v)}
            className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:hover:bg-slate-800 dark:hover:text-slate-100"
          >
            <PanelLeft className="size-4" />
          </button>
          {!sidebarOpen && (
            <>
              <span className="text-sm font-semibold tracking-tight">PaperTrace</span>
              <button
                type="button"
                aria-label="new chat"
                onClick={newChat}
                className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:hover:bg-slate-800 dark:hover:text-slate-100"
              >
                <Plus className="size-4" />
              </button>
            </>
          )}
        </header>
        <Chat
          key={activeId ?? "new"}
          messages={active?.messages ?? []}
          busy={busyId !== null}
          onAsk={(question) => void ask(question, modelId)}
          modelId={modelId}
          onModelChange={selectModel}
          onFeedback={(index, thumbs) => {
            if (activeId) setFeedback(activeId, index, thumbs);
          }}
        />
      </div>
    </div>
  );
}

/** Mirrors the API's SSE event contract (api/main.py -> core/agent.py stream_chat). */

export type Citation = { arxiv_id: string; title: string; url: string };

export type EvidenceRef = { arxiv_id: string | null; title: string | null };

export type ToolSummary = {
  evidence?: EvidenceRef[];
  groups?: Record<string, unknown>[];
  total?: number;
  sql?: string;
  note?: string;
  raw?: string;
};

export type StreamEvent =
  | { type: "token"; text: string }
  | { type: "tool_call"; name: string; args: Record<string, unknown> }
  | { type: "tool_result"; name: string; summary: ToolSummary; ms?: number | null }
  | { type: "done"; answer: string; citations: Citation[]; turn_id?: string }
  | { type: "error"; detail: string };

export type TraceStep = {
  name: string;
  args: Record<string, unknown>;
  summary?: ToolSummary;
  ms?: number | null;
};

export type AssistantMessage = {
  role: "assistant";
  turnId?: string;
  text: string;
  citations: Citation[];
  trace: TraceStep[];
  streaming: boolean;
  error?: string;
  feedback?: "up" | "down";
};

export type UserMessage = { role: "user"; text: string };

export type ChatMessage = UserMessage | AssistantMessage;

/** A client-side chat thread, persisted to localStorage. */
export type Conversation = {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messages: ChatMessage[];
};

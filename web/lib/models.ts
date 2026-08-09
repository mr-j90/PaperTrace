/** Mirrors CHAT_MODELS in api/main.py — ids the backend accepts on /chat. */

export type ModelOption = { id: string; label: string };

export const MODELS: ModelOption[] = [
  { id: "claude-haiku-4-5", label: "Claude Haiku 4.5" },
  { id: "claude-sonnet-5", label: "Claude Sonnet 5" },
  { id: "claude-opus-5", label: "Claude Opus 5" },
];

export const DEFAULT_MODEL_ID = MODELS[0].id;

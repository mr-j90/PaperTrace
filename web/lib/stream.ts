import type { StreamEvent } from "@/types/chat";

/** POST a question and yield parsed SSE events as they arrive. */
export async function* streamChat(
  question: string,
  signal?: AbortSignal,
): AsyncGenerator<StreamEvent> {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
    signal,
  });
  if (!response.ok || !response.body) {
    throw new Error(`chat request failed: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const parseFrame = (frame: string): StreamEvent | null => {
    const line = frame.trim();
    return line.startsWith("data: ") ? (JSON.parse(line.slice(6)) as StreamEvent) : null;
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split(/\r?\n\r?\n/);
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const event = parseFrame(frame);
      if (event) yield event;
    }
  }
  const tail = parseFrame(buffer);
  if (tail) yield tail;
}

import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

const API_URL = process.env.PAPERTRACE_API_URL ?? "http://localhost:8000";

/** Same-origin proxy to the FastAPI SSE endpoint — no CORS, API stays private. */
export async function POST(request: NextRequest) {
  const body = await request.text();
  const upstream = await fetch(`${API_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      "X-Accel-Buffering": "no",
    },
  });
}

import { NextRequest } from "next/server";

const API_URL = process.env.PAPERTRACE_API_URL ?? "http://localhost:8000";

export async function POST(request: NextRequest) {
  const upstream = await fetch(`${API_URL}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: await request.text(),
  });
  return new Response(null, { status: upstream.status });
}

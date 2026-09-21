import { NextResponse } from "next/server";
import { guardExpensiveMutation } from "@/lib/api-guard";
import { chatWithAgent, HarnessError, HarnessRuntimeUnavailable, toHarnessErrorJson } from "@/lib/harness";

export const dynamic = "force-dynamic";
export const maxDuration = 180;

// POST /api/harness/chat — the chat surfaces' entry point to the Eclipse Agent.
// Body: { query: string, history?: { role, content }[] }
//
// Same harness runtime as /api/harness/runs (prompt + tools + persistence), but
// shaped for conversation: it returns the agent's final text directly and has a
// chat-appropriate rate limit rather than the run limit.
export async function POST(request: Request) {
  const blocked = guardExpensiveMutation(request, "harness-chat", { limit: 60, windowMs: 5 * 60_000 });
  if (blocked) {
    return NextResponse.json(blocked.body, { status: blocked.status, headers: blocked.headers });
  }
  try {
    const body = await request.json().catch(() => ({}));
    const query = typeof (body as Record<string, unknown>).query === "string"
      ? ((body as Record<string, unknown>).query as string).trim()
      : "";
    if (!query) {
      return NextResponse.json({ error: "query is required" }, { status: 400 });
    }
    if (query.length > 4000) {
      return NextResponse.json({ error: "query too long (max 4000 chars)" }, { status: 400 });
    }

    const rawHistory = (body as Record<string, unknown>).history;
    const history = Array.isArray(rawHistory)
      ? rawHistory
          .filter(
            (t): t is { role: "user" | "assistant"; content: string } =>
              t !== null &&
              typeof t === "object" &&
              ((t as { role?: unknown }).role === "user" || (t as { role?: unknown }).role === "assistant") &&
              typeof (t as { content?: unknown }).content === "string"
          )
          .map((t) => ({ role: t.role, content: t.content }))
      : [];

    const result = await chatWithAgent(query, history);
    if (result.status === "failed") {
      return NextResponse.json(
        { success: false, error: result.error, runId: result.runId },
        { status: 502 }
      );
    }
    return NextResponse.json({ success: true, content: result.output, runId: result.runId });
  } catch (err) {
    const error = toHarnessErrorJson(err);
    const status =
      err instanceof HarnessRuntimeUnavailable ? 503
      : err instanceof HarnessError && err.code === "PROVIDER_NOT_CONFIGURED" ? 503
      : err instanceof HarnessError && err.code === "INVALID_INPUT" ? 400
      : 500;
    console.error("[api/harness/chat] POST error:", error.message);
    return NextResponse.json({ error: error.message, code: error.code }, { status });
  }
}

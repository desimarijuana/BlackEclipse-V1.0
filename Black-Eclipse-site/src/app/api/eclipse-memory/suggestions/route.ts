import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { listSuggestions, acceptSuggestion, dismissSuggestion } from "@/lib/harness/eclipse-memory-client";
import { isOperatorRequest } from "@/lib/harness/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/eclipse-memory/suggestions — inert Save/Dismiss proposals. A
// suggestion is NOT a memory and is never injected into a run.
export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const status = url.searchParams.get("status") || "pending";
    const suggestions = await listSuggestions(status);
    return NextResponse.json({ success: true, suggestions });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "suggestion list failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

// POST /api/eclipse-memory/suggestions/:id/accept|dismiss — operator-gated.
export async function POST(request: Request) {
  const blocked = guardMutation(request, "eclipse-memory-suggestion");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    if (!isOperatorRequest(request)) {
      return NextResponse.json({ error: "operator authorization required" }, { status: 403 });
    }
    const body = (await request.json().catch(() => ({}))) as { id?: string; action?: string; userId?: string };
    if (!body.id || !body.action) {
      return NextResponse.json({ error: "id and action are required" }, { status: 400 });
    }
    const result =
      body.action === "accept"
        ? await acceptSuggestion(body.id, true, body.userId)
        : await dismissSuggestion(body.id, true);
    return NextResponse.json(result, { status: 200 });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "suggestion action failed" },
      { status: unavailable ? 503 : 400 }
    );
  }
}

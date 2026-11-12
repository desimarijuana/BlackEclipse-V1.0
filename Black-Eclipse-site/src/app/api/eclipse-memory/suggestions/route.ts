import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { listSuggestionsPage, acceptSuggestion, dismissSuggestion } from "@/lib/harness/clients/eclipse-memory-client";
import { isOperatorRequest } from "@/lib/harness/clients/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/eclipse-memory/suggestions — inert Save/Dismiss proposals. A
// suggestion is NOT a memory and is never injected into a run.
//
// `scopeId` optionally narrows the list to one user scope. This app has no
// account system, so scope is caller-supplied; the authoritative cross-user
// guard is the mismatch refusal on accept/dismiss.
export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const status = url.searchParams.get("status") || "pending";
    const scopeId = url.searchParams.get("scopeId") || undefined;
    const limit = url.searchParams.get("limit") ? Number(url.searchParams.get("limit")) : 50;
    const offset = url.searchParams.get("offset") ? Number(url.searchParams.get("offset")) : 0;
    const page = await listSuggestionsPage(status, limit, offset, scopeId);
    return NextResponse.json({ success: true, ...page });
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
        : await dismissSuggestion(body.id, true, body.userId);
    return NextResponse.json(result, { status: 200 });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "suggestion action failed" },
      { status: unavailable ? 503 : 400 }
    );
  }
}

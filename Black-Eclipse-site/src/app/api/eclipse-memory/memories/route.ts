import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { listMemories, createMemory } from "@/lib/harness/eclipse-memory-client";
import { isOperatorRequest } from "@/lib/harness/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/eclipse-memory/memories — the memory explorer list.
export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const memories = await listMemories({
      memoryType: url.searchParams.get("memoryType") || undefined,
      scope: url.searchParams.get("scope") || undefined,
      status: url.searchParams.get("status") || undefined,
      scopeId: url.searchParams.get("scopeId") || undefined,
      limit: url.searchParams.get("limit") ? Number(url.searchParams.get("limit")) : undefined,
    });
    return NextResponse.json({ success: true, memories });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "memory list failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

// POST /api/eclipse-memory/memories — explicit save (operator-gated in Python).
export async function POST(request: Request) {
  const blocked = guardMutation(request, "eclipse-memory-write");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const content = typeof body.content === "string" ? body.content.trim() : "";
    if (!content) return NextResponse.json({ error: "content is required" }, { status: 400 });
    const memory = await createMemory(
      {
        memoryType: typeof body.memoryType === "string" ? body.memoryType : "semantic",
        content,
        source: typeof body.source === "string" ? body.source : "manual",
        scope: typeof body.scope === "string" ? body.scope : "general",
        scopeId: typeof body.scopeId === "string" ? body.scopeId : undefined,
        subject: typeof body.subject === "string" ? body.subject : undefined,
        confidence: typeof body.confidence === "number" ? body.confidence : undefined,
        verification: typeof body.verification === "string" ? body.verification : undefined,
      },
      isOperatorRequest(request)
    );
    return NextResponse.json({ success: true, memory });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "memory save failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

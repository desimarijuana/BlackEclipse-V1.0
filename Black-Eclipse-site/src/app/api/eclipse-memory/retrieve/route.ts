import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { retrieveMemories } from "@/lib/harness/clients/eclipse-memory-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/eclipse-memory/retrieve — the retrieval pipeline (read-only).
export async function POST(request: Request) {
  const blocked = guardMutation(request, "eclipse-memory-retrieve");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const query = typeof body.query === "string" ? body.query : "";
    const result = await retrieveMemories({
      query,
      types: Array.isArray(body.types) ? (body.types as string[]) : undefined,
      actorScope: typeof body.actorScope === "string" ? body.actorScope : undefined,
      scopeId: typeof body.scopeId === "string" ? body.scopeId : undefined,
      subject: typeof body.subject === "string" ? body.subject : undefined,
      budgetChars: typeof body.budgetChars === "number" ? body.budgetChars : undefined,
      limit: typeof body.limit === "number" ? body.limit : undefined,
    });
    return NextResponse.json({ success: true, ...result });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "retrieval failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

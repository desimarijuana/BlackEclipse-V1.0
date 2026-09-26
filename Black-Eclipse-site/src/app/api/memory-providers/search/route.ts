import { NextResponse } from "next/server";
import { memoryProviderSearch } from "@/lib/harness/eclipse-memory-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/memory-providers/search — native-first search with explicit,
// fenced external search. External results are never promoted to native.
export async function POST(request: Request) {
  try {
    const payload = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const body = await memoryProviderSearch({
      query: String(payload.query ?? ""),
      scopeId: payload.scopeId ? String(payload.scopeId) : undefined,
      limit: typeof payload.limit === "number" ? payload.limit : undefined,
      allowExternal: Boolean(payload.allowExternal),
    });
    return NextResponse.json(body);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "provider search failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

import { NextResponse } from "next/server";
import { memoryProviderSearch } from "@/lib/harness/clients/eclipse-memory-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";
import { guardMutation } from "@/lib/api-guard";

export const dynamic = "force-dynamic";

// POST /api/memory-providers/search — native-first search with explicit,
// fenced external search. External results are never promoted to native.
export async function POST(request: Request) {
  // Although search is read-shaped, it performs an OUTBOUND call to external
  // memory providers when `allowExternal` is set, so it is operator-gated like
  // every other expensive/external mutation.
  const blocked = guardMutation(request, "memory-providers-search");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
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

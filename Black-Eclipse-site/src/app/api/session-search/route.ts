import { NextResponse } from "next/server";
import { sessionSearch } from "@/lib/harness/clients/eclipse-memory-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/session-search — full-text search over prior Eclipse sessions.
// Historical content is context, never current financial evidence.
export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const q = url.searchParams.get("q");
    if (!q) {
      return NextResponse.json({ error: "q is required" }, { status: 400 });
    }
    const result = await sessionSearch({
      q,
      scopeId: url.searchParams.get("scopeId") || undefined,
      scope: url.searchParams.get("scope") || undefined,
      runId: url.searchParams.get("runId") || undefined,
      dateFrom: url.searchParams.get("dateFrom") || undefined,
      dateTo: url.searchParams.get("dateTo") || undefined,
      limit: url.searchParams.get("limit") ? Number(url.searchParams.get("limit")) : undefined,
      offset: url.searchParams.get("offset") ? Number(url.searchParams.get("offset")) : undefined,
    });
    return NextResponse.json({ success: true, ...result });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "session search failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

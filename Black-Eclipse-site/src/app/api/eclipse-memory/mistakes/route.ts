import { NextResponse } from "next/server";
import { listMistakesPage } from "@/lib/harness/clients/eclipse-memory-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/eclipse-memory/mistakes — captured mistakes/recoveries.
export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const limit = url.searchParams.get("limit") ? Number(url.searchParams.get("limit")) : 50;
    const offset = url.searchParams.get("offset") ? Number(url.searchParams.get("offset")) : 0;
    const page = await listMistakesPage(limit, offset);
    return NextResponse.json({ success: true, mistakes: page.items, total: page.total, limit: page.limit, offset: page.offset, hasMore: page.hasMore });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "mistakes failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

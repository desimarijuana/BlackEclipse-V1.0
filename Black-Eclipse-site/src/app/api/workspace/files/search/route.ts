import { NextResponse } from "next/server";
import { searchWorkspaceFiles } from "@/lib/harness/clients/code-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/workspace/files/search?q=..&rootId=.. — bounded project-file search
// for the composer's `@` palette and the file picker. Read-only; the runtime
// confines the walk to the active (or named) approved root.
export async function GET(request: Request) {
  try {
    const params = new URL(request.url).searchParams;
    const q = params.get("q") ?? "";
    const rootId = params.get("rootId");
    const limit = Number(params.get("limit") ?? 50) || 50;
    const result = await searchWorkspaceFiles(q, rootId, limit);
    return NextResponse.json({ success: true, ...result });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "search failed" },
      { status: unavailable ? 503 : 400 },
    );
  }
}

import { NextResponse } from "next/server";
import { listWorkspaceFiles } from "@/lib/harness/code-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/workspace/files?path=.&rootId=.. — the editor file tree (direct children).
export async function GET(request: Request) {
  try {
    const params = new URL(request.url).searchParams;
    const path = params.get("path") ?? ".";
    const rootId = params.get("rootId");
    const result = await listWorkspaceFiles(path, rootId);
    return NextResponse.json({ success: true, ...result });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "list failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}

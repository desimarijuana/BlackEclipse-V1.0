import { NextResponse } from "next/server";
import { listWorkspaceFiles } from "@/lib/harness/code-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/workspace/files?path=. — the editor file tree (direct children).
export async function GET(request: Request) {
  try {
    const path = new URL(request.url).searchParams.get("path") ?? ".";
    const result = await listWorkspaceFiles(path);
    return NextResponse.json({ success: true, ...result });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "list failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}

import { NextResponse } from "next/server";
import { readWorkspaceFile } from "@/lib/harness/code-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/workspace/file/read — read one file inside the active root.
export async function POST(request: Request) {
  try {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const path = typeof body.path === "string" ? body.path : "";
    if (!path) return NextResponse.json({ error: "path is required" }, { status: 400 });
    const rootId = typeof body.rootId === "string" ? body.rootId : undefined;
    const result = await readWorkspaceFile(path, rootId);
    return NextResponse.json({ success: true, ...result });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "read failed" },
      { status: unavailable ? 503 : 400 },
    );
  }
}

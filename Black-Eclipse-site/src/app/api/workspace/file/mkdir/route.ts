import { NextResponse } from "next/server";
import { makeWorkspaceFolder } from "@/lib/harness/clients/code-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/workspace/file/mkdir — create a folder inside the active root.
export async function POST(request: Request) {
  try {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const path = typeof body.path === "string" ? body.path : "";
    if (!path) return NextResponse.json({ error: "path is required" }, { status: 400 });
    const result = await makeWorkspaceFolder(path);
    return NextResponse.json({ success: true, ...result });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "mkdir failed" },
      { status: unavailable ? 503 : 400 },
    );
  }
}

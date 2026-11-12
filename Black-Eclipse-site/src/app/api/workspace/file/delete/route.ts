import { NextResponse } from "next/server";
import { deleteWorkspacePath } from "@/lib/harness/clients/code-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/workspace/file/delete — delete a file / empty folder in the root.
export async function POST(request: Request) {
  try {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const path = typeof body.path === "string" ? body.path : "";
    if (!path) return NextResponse.json({ error: "path is required" }, { status: 400 });
    const result = await deleteWorkspacePath(path);
    return NextResponse.json({ success: true, ...result });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "delete failed" },
      { status: unavailable ? 503 : 400 },
    );
  }
}

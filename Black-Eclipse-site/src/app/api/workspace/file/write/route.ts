import { NextResponse } from "next/server";
import { writeWorkspaceFile } from "@/lib/harness/clients/code-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/workspace/file/write — save one file inside the active root.
export async function POST(request: Request) {
  try {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const path = typeof body.path === "string" ? body.path : "";
    const content = typeof body.content === "string" ? body.content : "";
    if (!path) return NextResponse.json({ error: "path is required" }, { status: 400 });
    const result = await writeWorkspaceFile(path, content);
    return NextResponse.json({ success: true, ...result });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "save failed" },
      { status: unavailable ? 503 : 400 },
    );
  }
}

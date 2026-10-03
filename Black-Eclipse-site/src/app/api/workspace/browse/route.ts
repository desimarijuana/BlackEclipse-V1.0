import { NextResponse } from "next/server";
import { browseFolders } from "@/lib/harness/code-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/workspace/browse?path= — list direct children of a folder for the
// picker. Read-only; the runtime enforces operator (loopback/token) access.
export async function GET(request: Request) {
  try {
    const path = new URL(request.url).searchParams.get("path") ?? undefined;
    const result = await browseFolders(path);
    return NextResponse.json({ success: true, ...result });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "browse failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}

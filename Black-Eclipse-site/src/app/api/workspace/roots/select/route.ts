import { NextResponse } from "next/server";
import { selectTrustedRoot } from "@/lib/harness/clients/code-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";
import { corsPreflight, localCors } from "@/lib/workspace/cors";

export const dynamic = "force-dynamic";

// POST /api/workspace/roots/select — make an approved folder the active
// workspace, or clear the selection with a null rootId.
export async function POST(request: Request) {
  try {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const rootId = typeof body.rootId === "string" ? body.rootId : null;
    const selected = await selectTrustedRoot(rootId);
    return NextResponse.json({ success: true, selected }, { headers: localCors(request) });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "select failed" },
      { status: unavailable ? 503 : 400, headers: localCors(request) },
    );
  }
}

export async function OPTIONS(request: Request) {
  return corsPreflight(request);
}

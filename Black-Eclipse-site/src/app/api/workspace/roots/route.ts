import { NextResponse } from "next/server";
import { approveTrustedRoot, listTrustedRoots } from "@/lib/harness/code-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";
import { corsPreflight, localCors } from "@/lib/workspace/cors";

export const dynamic = "force-dynamic";

// GET  /api/workspace/roots — the approved workspace folders.
// POST /api/workspace/roots — approve a folder (the picker's "open" action).
export async function GET(request: Request) {
  try {
    const roots = await listTrustedRoots();
    return NextResponse.json({ success: true, roots }, { headers: localCors(request) });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "roots lookup failed" },
      { status: unavailable ? 503 : 500, headers: localCors(request) },
    );
  }
}

export async function POST(request: Request) {
  try {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const path = typeof body.path === "string" ? body.path : "";
    if (!path) {
      return NextResponse.json(
        { error: "path is required" },
        { status: 400, headers: localCors(request) },
      );
    }
    const label = typeof body.label === "string" ? body.label : undefined;
    const root = await approveTrustedRoot(path, label);
    return NextResponse.json({ success: true, root }, { headers: localCors(request) });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "approve failed" },
      { status: unavailable ? 503 : 400, headers: localCors(request) },
    );
  }
}

export async function OPTIONS(request: Request) {
  return corsPreflight(request);
}

import { NextResponse } from "next/server";
import { listStandingGrants } from "@/lib/harness/grants-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/harness/grants — the standing "always allow" permissions.
export async function GET(request: Request) {
  try {
    const scope = new URL(request.url).searchParams.get("scope") || undefined;
    const grants = await listStandingGrants(scope);
    return NextResponse.json({ success: true, grants });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Grant list failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

import { NextResponse } from "next/server";
import { listSkills } from "@/lib/harness/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/skills — the Skills Library. Python owns the registry; this proxies.
export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const status = url.searchParams.get("status") || undefined;
    const data = await listSkills(status);
    return NextResponse.json({ success: true, ...data });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "skill list failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

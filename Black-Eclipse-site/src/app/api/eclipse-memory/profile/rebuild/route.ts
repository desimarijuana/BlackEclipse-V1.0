import { NextResponse } from "next/server";
import { rebuildProfile } from "@/lib/harness/clients/eclipse-memory-client";
import { guardMutation } from "@/lib/api-guard";
import { isOperatorRequest } from "@/lib/harness/clients/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/eclipse-memory/profile/rebuild — operator-gated: materialize and
// PERSIST a fresh profile snapshot. It never writes or alters a memory record.
export async function POST(request: Request) {
  const blocked = guardMutation(request, "eclipse-memory-profile-rebuild");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    if (!isOperatorRequest(request)) {
      return NextResponse.json({ error: "operator authorization required" }, { status: 403 });
    }
    const body = (await request.json().catch(() => ({}))) as { scopeId?: string };
    const result = await rebuildProfile(true, body.scopeId);
    return NextResponse.json(result);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "profile rebuild failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

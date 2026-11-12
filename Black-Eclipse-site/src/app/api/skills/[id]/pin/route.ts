import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { pinSkillVersion } from "@/lib/harness/clients/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/skills/:id/pin — operator-gated pin/unpin of a skill version.
// Pinning is orthogonal to status: it only exempts a version from automatic
// staleness/archive maintenance.
export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const blocked = guardMutation(request, "skill-pin");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const data = await pinSkillVersion(
      id,
      typeof body.version === "string" ? body.version : undefined,
      body.pinned !== false
    );
    return NextResponse.json(data);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "pin failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

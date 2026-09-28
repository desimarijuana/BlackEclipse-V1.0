import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { approveProjectSkill, isOperatorRequest } from "@/lib/harness/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/skills/project/approve — re-approve a quarantined (drifted) project
// root, re-baselining its content hash. Operator-gated.
export async function POST(request: Request) {
  const blocked = guardMutation(request, "skill-project-approve");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  if (!isOperatorRequest(request)) {
    return NextResponse.json({ error: "operator authorization required" }, { status: 403 });
  }
  try {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const path = typeof body.path === "string" ? body.path : undefined;
    const note = typeof body.note === "string" ? body.note : undefined;
    await approveProjectSkill(path, note);
    return NextResponse.json({ success: true });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "approve failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

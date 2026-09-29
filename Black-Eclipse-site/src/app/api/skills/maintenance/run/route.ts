import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { runSkillMaintenance } from "@/lib/harness/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/skills/maintenance/run — operator-gated maintenance pass.
// Report-only by default; never deletes, never enables, pinned skills exempt.
export async function POST(request: Request) {
  const blocked = guardMutation(request, "skill-maintenance-run");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const data = await runSkillMaintenance();
    return NextResponse.json(data);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "maintenance run failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

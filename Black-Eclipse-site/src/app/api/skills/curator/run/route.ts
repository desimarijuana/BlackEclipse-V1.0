import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { runSkillCurator } from "@/lib/harness/clients/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/skills/curator/run — operator-gated curator pass.
// dry_run is the default; a merge always lands as an inert draft.
export async function POST(request: Request) {
  const blocked = guardMutation(request, "skill-curator-run");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    let mode: "dry_run" | "propose" | "apply" | undefined;
    try {
      const body = (await request.json()) as { mode?: string };
      if (body?.mode === "dry_run" || body?.mode === "propose" || body?.mode === "apply") {
        mode = body.mode;
      }
    } catch {
      // no body: use the configured default
    }
    const data = await runSkillCurator(mode);
    return NextResponse.json(data);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "curator run failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

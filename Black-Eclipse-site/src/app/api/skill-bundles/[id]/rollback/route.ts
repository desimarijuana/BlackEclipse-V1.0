import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { rollbackSkillBundle, isOperatorRequest } from "@/lib/harness/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/skill-bundles/:id/rollback — re-pin the recorded lock (safe rollback).
export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const blocked = guardMutation(request, "skill-bundle-rollback");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  if (!isOperatorRequest(request)) {
    return NextResponse.json({ error: "operator authorization required" }, { status: 403 });
  }
  try {
    return NextResponse.json(await rollbackSkillBundle(id));
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "rollback failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

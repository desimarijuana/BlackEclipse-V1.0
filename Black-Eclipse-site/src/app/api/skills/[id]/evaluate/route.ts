import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { evaluateSkill } from "@/lib/harness/clients/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";
export const maxDuration = 120;

// POST /api/skills/:id/evaluate — deterministic evaluation of a skill version.
export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardMutation(request, "skill-evaluate");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const { id } = await params;
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const result = await evaluateSkill(
      id,
      typeof body.version === "string" ? body.version : undefined,
      body.runRegression === true
    );
    return NextResponse.json({ success: result.ok !== false, ...result });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "evaluation failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

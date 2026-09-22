import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { validateSkillInput } from "@/lib/harness/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/skills/validate-input — validate a skill's input against its schema.
export async function POST(request: Request) {
  const blocked = guardMutation(request, "skills-validate-input");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const skillId = typeof body.skillId === "string" ? body.skillId : "";
    if (!skillId) return NextResponse.json({ error: "skillId is required" }, { status: 400 });
    const input = body.input && typeof body.input === "object" ? (body.input as Record<string, unknown>) : {};
    const result = await validateSkillInput(skillId, input);
    return NextResponse.json({ success: true, ...result });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "validation failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

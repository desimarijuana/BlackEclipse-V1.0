import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { createUserSkill, isOperatorRequest } from "@/lib/harness/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/skills/author — create a user-authored skill (operator-gated).
export async function POST(request: Request) {
  const blocked = guardMutation(request, "skills-author");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const name = typeof body.name === "string" ? body.name.trim() : "";
    const instructions = typeof body.instructions === "string" ? body.instructions : "";
    if (!name) return NextResponse.json({ error: "name is required" }, { status: 400 });
    if (!instructions.trim()) return NextResponse.json({ error: "instructions are required" }, { status: 400 });

    const result = await createUserSkill(
      {
        name,
        description: typeof body.description === "string" ? body.description : "",
        instructions,
        category: typeof body.category === "string" ? body.category : undefined,
        tags: Array.isArray(body.tags) ? (body.tags as string[]) : undefined,
        requiredTools: Array.isArray(body.requiredTools) ? (body.requiredTools as string[]) : undefined,
        permissions: Array.isArray(body.permissions) ? (body.permissions as string[]) : undefined,
        riskLevel: typeof body.riskLevel === "string" ? body.riskLevel : undefined,
        skillId: typeof body.skillId === "string" ? body.skillId : undefined,
      },
      isOperatorRequest(request)
    );
    return NextResponse.json(result);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "skill creation failed" },
      { status: unavailable ? 503 : 400 }
    );
  }
}

import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { updateUserSkill, deleteUserSkill, isOperatorRequest } from "@/lib/harness/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// PUT /api/skills/:id/author — edit a user skill (creates a new version).
export async function PUT(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardMutation(request, "skills-author-update");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const { id } = await params;
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const result = await updateUserSkill(
      id,
      {
        name: typeof body.name === "string" ? body.name : undefined,
        description: typeof body.description === "string" ? body.description : undefined,
        instructions: typeof body.instructions === "string" ? body.instructions : undefined,
        category: typeof body.category === "string" ? body.category : undefined,
        tags: Array.isArray(body.tags) ? (body.tags as string[]) : undefined,
        requiredTools: Array.isArray(body.requiredTools) ? (body.requiredTools as string[]) : undefined,
        permissions: Array.isArray(body.permissions) ? (body.permissions as string[]) : undefined,
        riskLevel: typeof body.riskLevel === "string" ? body.riskLevel : undefined,
      },
      isOperatorRequest(request)
    );
    return NextResponse.json(result);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "skill update failed" },
      { status: unavailable ? 503 : 400 }
    );
  }
}

// DELETE /api/skills/:id/author — delete a user skill (built-ins refused).
export async function DELETE(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardMutation(request, "skills-author-delete");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const { id } = await params;
    const result = await deleteUserSkill(id, isOperatorRequest(request));
    return NextResponse.json(result);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "skill delete failed" },
      { status: unavailable ? 503 : 400 }
    );
  }
}

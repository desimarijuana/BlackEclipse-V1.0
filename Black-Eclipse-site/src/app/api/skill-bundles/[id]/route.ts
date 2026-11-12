import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { deleteSkillBundle, isOperatorRequest } from "@/lib/harness/clients/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// DELETE /api/skill-bundles/:id — delete a bundle (operator-gated).
export async function DELETE(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const blocked = guardMutation(request, "skill-bundle-delete");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  if (!isOperatorRequest(request)) {
    return NextResponse.json({ error: "operator authorization required" }, { status: 403 });
  }
  try {
    await deleteSkillBundle(id);
    return NextResponse.json({ success: true });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "bundle delete failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { lockSkillBundle, unlockSkillBundle, isOperatorRequest } from "@/lib/harness/clients/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/skill-bundles/:id/lock — pin member versions (reproducible).
export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const blocked = guardMutation(request, "skill-bundle-lock");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  if (!isOperatorRequest(request)) {
    return NextResponse.json({ error: "operator authorization required" }, { status: 403 });
  }
  try {
    return NextResponse.json(await lockSkillBundle(id));
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "lock failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

// DELETE /api/skill-bundles/:id/lock — unlock.
export async function DELETE(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const blocked = guardMutation(request, "skill-bundle-unlock");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  if (!isOperatorRequest(request)) {
    return NextResponse.json({ error: "operator authorization required" }, { status: 403 });
  }
  try {
    return NextResponse.json(await unlockSkillBundle(id));
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "unlock failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

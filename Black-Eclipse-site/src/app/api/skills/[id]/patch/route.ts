import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { isOperatorRequest, proposeSkillPatch } from "@/lib/harness/skills-client";
import type { SkillPatchOperation } from "@/lib/harness/skills-types";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/skills/:id/patch — propose a structured patch. Creates a NEW inert
// version; the active version is never mutated. A stale base version is refused.
export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const blocked = guardMutation(request, "skill-patch");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const operations = Array.isArray(body.operations) ? (body.operations as SkillPatchOperation[]) : [];
    if (!body.baseVersion || operations.length === 0) {
      return NextResponse.json({ error: "baseVersion and operations are required" }, { status: 400 });
    }
    const result = await proposeSkillPatch(id, {
      baseVersion: String(body.baseVersion),
      operations,
      reason: typeof body.reason === "string" ? body.reason : undefined,
      author: typeof body.author === "string" ? body.author : undefined,
      reviewId: typeof body.reviewId === "string" ? body.reviewId : undefined,
      sourceRunId: typeof body.sourceRunId === "string" ? body.sourceRunId : undefined,
      operator: isOperatorRequest(request),
    });
    return NextResponse.json(result, { status: (result as { ok?: boolean }).ok ? 200 : 403 });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "patch proposal failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { generateDraft, rejectCandidate, isOperatorRequest } from "@/lib/harness/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/learning/candidates/:id/:action — generate-draft | reject.
// Both require operator authorization, derived server-side.
export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string; action: string }> }
) {
  const { id, action } = await params;
  if (action !== "generate-draft" && action !== "reject") {
    return NextResponse.json({ error: "unsupported action" }, { status: 404 });
  }
  const blocked = guardMutation(request, `learning-${action}`);
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const operator = isOperatorRequest(request);
    const result =
      action === "generate-draft"
        ? await generateDraft(id, operator)
        : await rejectCandidate(id, operator);
    return NextResponse.json(result, { status: result.ok ? 200 : 403 });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : `${action} failed` },
      { status: unavailable ? 503 : 500 }
    );
  }
}

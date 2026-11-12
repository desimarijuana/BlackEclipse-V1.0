import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import {
  submitDraftReview,
  approveDraft,
  rejectDraft,
  isOperatorRequest,
} from "@/lib/harness/clients/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/skill-drafts/:id/:action — submit-review | approve | reject.
// Draft promotion is operator-only; a client cannot self-approve.
const ACTIONS = new Set(["submit-review", "approve", "reject"]);

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string; action: string }> }
) {
  const { id, action } = await params;
  if (!ACTIONS.has(action)) {
    return NextResponse.json({ error: "unsupported action" }, { status: 404 });
  }
  const blocked = guardMutation(request, `skill-draft-${action}`);
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const operator = isOperatorRequest(request);
    const requestId = typeof body.requestId === "string" ? body.requestId : "";
    let result: Record<string, unknown>;
    if (action === "submit-review") {
      result = (await submitDraftReview(
        id, operator,
        typeof body.reason === "string" ? body.reason : "submit for review",
        typeof body.evaluationId === "string" ? body.evaluationId : undefined
      )) as Record<string, unknown>;
    } else if (action === "approve") {
      if (!requestId) return NextResponse.json({ error: "requestId is required" }, { status: 400 });
      result = (await approveDraft(id, operator, requestId, typeof body.notes === "string" ? body.notes : "")) as Record<string, unknown>;
    } else {
      if (!requestId) return NextResponse.json({ error: "requestId is required" }, { status: 400 });
      result = (await rejectDraft(id, operator, requestId, typeof body.reason === "string" ? body.reason : "rejected")) as Record<string, unknown>;
    }
    return NextResponse.json(result, { status: result.success ? 200 : 403 });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : `${action} failed` },
      { status: unavailable ? 503 : 500 }
    );
  }
}

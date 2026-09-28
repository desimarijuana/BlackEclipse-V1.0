import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { learnFromSource, isOperatorRequest } from "@/lib/harness/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";
import type { LearnRequest } from "@/lib/harness/skills-types";

export const dynamic = "force-dynamic";

// POST /api/learning/from-source — guided `/learn`. Produces an inert skill
// draft from a run/document/repo/repeated-workflow/correction. Operator-gated.
export async function POST(request: Request) {
  const blocked = guardMutation(request, "learn-from-source");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  if (!isOperatorRequest(request)) {
    return NextResponse.json({ error: "operator authorization required" }, { status: 403 });
  }
  try {
    const body = (await request.json().catch(() => ({}))) as LearnRequest;
    if (!body.title || !body.sourceKind) {
      return NextResponse.json({ error: "sourceKind and title are required" }, { status: 400 });
    }
    const result = await learnFromSource(body);
    return NextResponse.json(result, { status: result.ok ? 200 : 400 });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "learn failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { learnPreferences } from "@/lib/harness/eclipse-memory-client";
import { isOperatorRequest } from "@/lib/harness/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/eclipse-memory/preferences/learn — run the deterministic preference
// learner now. Operator-gated. It creates INERT suggestions only; accepting one
// remains the existing suggestion route and the ONE memory write gate.
export async function POST(request: Request) {
  const blocked = guardMutation(request, "eclipse-memory-preferences-learn");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    if (!isOperatorRequest(request)) {
      return NextResponse.json({ error: "operator authorization required" }, { status: 403 });
    }
    const body = (await request.json().catch(() => ({}))) as { userId?: string; runId?: string };
    const result = await learnPreferences(body.userId, body.runId);
    return NextResponse.json(result);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "preference learning failed" },
      { status: unavailable ? 503 : 400 }
    );
  }
}

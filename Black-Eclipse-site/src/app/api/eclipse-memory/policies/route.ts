import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { getPolicies, updatePolicies } from "@/lib/harness/eclipse-memory-client";
import { isOperatorRequest } from "@/lib/harness/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/eclipse-memory/policies — current policy + defaults/bounds.
export async function GET() {
  try {
    return NextResponse.json({ success: true, ...(await getPolicies()) });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "policy read failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

// PUT /api/eclipse-memory/policies — operator-only policy changes.
export async function PUT(request: Request) {
  const blocked = guardMutation(request, "eclipse-memory-policies");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    if (!isOperatorRequest(request)) {
      return NextResponse.json({ error: "operator authorization required" }, { status: 403 });
    }
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const policies = (body.policies && typeof body.policies === "object") ? body.policies as Record<string, unknown> : {};
    const result = await updatePolicies(policies, true);
    return NextResponse.json(result);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "policy update failed" },
      { status: unavailable ? 503 : 400 }
    );
  }
}

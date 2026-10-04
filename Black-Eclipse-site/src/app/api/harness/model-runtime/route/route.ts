import { NextResponse } from "next/server";
import { routeModel, HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/harness/model-runtime/route — pure routing computation: given a task
// (or an explicit model), return the decision trace (candidates, scores, reason).
// No provider is called; no credentials are involved.
export async function POST(request: Request) {
  try {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const decision = await routeModel({
      model: typeof body.model === "string" ? body.model : undefined,
      task: typeof body.task === "string" ? body.task : undefined,
      requirements: (body.requirements as Record<string, unknown>) ?? undefined,
      policy: (body.policy as Record<string, unknown>) ?? undefined,
    });
    return NextResponse.json({ success: true, decision });
  } catch (err) {
    const status = err instanceof HarnessRuntimeUnavailable ? 503 : 500;
    console.error("[api/harness/model-runtime/route] POST error:", err);
    return NextResponse.json({ error: "Failed to compute route" }, { status });
  }
}

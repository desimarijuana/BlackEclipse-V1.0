import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { listCorrections, createCorrection } from "@/lib/harness/eclipse-memory-client";
import { isOperatorRequest } from "@/lib/harness/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/eclipse-memory/corrections — recorded corrections.
export async function GET() {
  try {
    return NextResponse.json({ success: true, corrections: await listCorrections() });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "corrections failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

// POST /api/eclipse-memory/corrections — record a user correction (operator-gated).
export async function POST(request: Request) {
  const blocked = guardMutation(request, "eclipse-memory-correction");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const wrong = typeof body.wrong === "string" ? body.wrong.trim() : "";
    const correction = typeof body.correction === "string" ? body.correction.trim() : "";
    if (!wrong || !correction) {
      return NextResponse.json({ error: "wrong and correction are required" }, { status: 400 });
    }
    if (!isOperatorRequest(request)) {
      return NextResponse.json({ error: "operator authorization required" }, { status: 403 });
    }
    const result = await createCorrection(
      {
        wrong,
        correction,
        subject: typeof body.subject === "string" ? body.subject : undefined,
        runId: typeof body.runId === "string" ? body.runId : undefined,
        scope: typeof body.scope === "string" ? body.scope : "user",
        generalizable: body.generalizable === true,
      },
      true
    );
    return NextResponse.json(result);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "correction failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

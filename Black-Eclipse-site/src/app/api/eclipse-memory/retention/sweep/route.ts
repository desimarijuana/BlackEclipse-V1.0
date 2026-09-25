import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { retentionSweep } from "@/lib/harness/eclipse-memory-client";
import { isOperatorRequest } from "@/lib/harness/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/eclipse-memory/retention/sweep — apply retention to automatic memory.
export async function POST(request: Request) {
  const blocked = guardMutation(request, "eclipse-memory-retention-sweep");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    if (!isOperatorRequest(request)) {
      return NextResponse.json({ error: "operator authorization required" }, { status: 403 });
    }
    const result = await retentionSweep(true);
    return NextResponse.json(result);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "retention sweep failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { resetMCPCircuit } from "@/lib/harness/mcp-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/harness/mcp/servers/:id/circuit/reset — operator reset of a server's
// circuit breaker. A server that connects but fails every call trips the breaker
// into OPEN and is not re-probed until its cooldown; this clears it immediately.
export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardMutation(request, "mcp-circuit-reset");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const { id } = await params;
    const result = await resetMCPCircuit(id);
    return NextResponse.json({ ...result, success: true });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Circuit reset failed" },
      { status: unavailable ? 503 : 400 }
    );
  }
}

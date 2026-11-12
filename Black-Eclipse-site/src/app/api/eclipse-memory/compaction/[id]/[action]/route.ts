import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { acceptCompaction, rejectCompaction } from "@/lib/harness/clients/eclipse-memory-client";
import { isOperatorRequest } from "@/lib/harness/clients/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/eclipse-memory/compaction/:id/:action — accept | reject. Operator-gated.
const ACTIONS = new Set(["accept", "reject"]);

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string; action: string }> }
) {
  const { id, action } = await params;
  if (!ACTIONS.has(action)) {
    return NextResponse.json({ error: `unsupported action: ${action}` }, { status: 404 });
  }
  const blocked = guardMutation(request, `memory-compaction-${action}`);
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  if (!isOperatorRequest(request)) {
    return NextResponse.json({ error: "operator authorization required" }, { status: 403 });
  }
  try {
    const body = (await request.json().catch(() => ({}))) as { mergedContent?: string };
    const result = action === "accept"
      ? await acceptCompaction(id, body.mergedContent)
      : await rejectCompaction(id);
    return NextResponse.json(result, { status: result.ok ? 200 : 400 });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : `${action} failed` },
      { status: unavailable ? 503 : 500 }
    );
  }
}

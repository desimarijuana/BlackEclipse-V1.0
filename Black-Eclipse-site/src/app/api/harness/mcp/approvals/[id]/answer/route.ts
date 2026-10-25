import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { answerClarification } from "@/lib/harness/mcp-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/harness/mcp/approvals/:id/answer — answer a paused `clarify`
// question. This is NOT an approval: it only resolves a human-in-the-loop
// question, and the runtime refuses any row that is not a clarification.
export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardMutation(request, "mcp-clarification-answer");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const { id } = await params;
    const body = (await request.json().catch(() => ({}))) as { answer?: unknown };
    if (typeof body.answer !== "string") {
      return NextResponse.json({ error: "answer must be a string" }, { status: 400 });
    }
    const clarification = await answerClarification(id, body.answer);
    return NextResponse.json({ success: true, clarification });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    const notFound = err instanceof Error && /404/.test(err.message);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Clarification answer failed" },
      { status: unavailable ? 503 : notFound ? 404 : 400 }
    );
  }
}

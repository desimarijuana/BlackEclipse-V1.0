import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { forgetConversation } from "@/lib/harness/eclipse-memory-client";
import { isOperatorRequest } from "@/lib/harness/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/eclipse-memory/conversations/[conversationId]/forget — archive one
// conversation's PRIVATE memory (a bot's, or a group-room member's bucket).
// Operator-gated; the Python runtime enforces authorization independently.
export async function POST(request: Request, { params }: { params: Promise<{ conversationId: string }> }) {
  const blocked = guardMutation(request, "eclipse-memory-conversation-forget");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    if (!isOperatorRequest(request)) {
      return NextResponse.json({ error: "operator authorization required" }, { status: 403 });
    }
    const { conversationId } = await params;
    const result = await forgetConversation(conversationId, true);
    return NextResponse.json(result);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "conversation forget failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

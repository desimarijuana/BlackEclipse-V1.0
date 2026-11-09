import { NextResponse } from "next/server";
import { guardExpensiveMutation } from "@/lib/api-guard";
import { SessionError, cloneSessionContext } from "@/lib/chat/session-store";

export const dynamic = "force-dynamic";

// /api/chat/session/clone
//
// POST { fromChatId, toChatId } → { success, copied }
//
// Forking a conversation creates a new chat id; its copied attachments still
// reference file names, and the run reads context from the NEW session folder.
// This copies only CONTEXT documents. Output files and checkpoints belong to
// the source runs and are deliberately not cloned.

function statusFor(err: unknown): { status: number; body: { error: string; code?: string } } {
  if (err instanceof SessionError) {
    return { status: 400, body: { error: err.message, code: err.code } };
  }
  console.error("[api/chat/session/clone] error:", err);
  return { status: 500, body: { error: "Session clone failed" } };
}

export async function POST(request: Request) {
  const blocked = guardExpensiveMutation(request, "chat-session-clone", { limit: 60, windowMs: 60_000 });
  if (blocked) {
    return NextResponse.json(blocked.body, { status: blocked.status, headers: blocked.headers });
  }
  try {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const fromChatId = typeof body.fromChatId === "string" ? body.fromChatId : "";
    const toChatId = typeof body.toChatId === "string" ? body.toChatId : "";
    if (!fromChatId || !toChatId) {
      return NextResponse.json({ error: "fromChatId and toChatId are required" }, { status: 400 });
    }
    const result = await cloneSessionContext(fromChatId, toChatId);
    return NextResponse.json({ success: true, copied: result.copied });
  } catch (err) {
    const { status, body } = statusFor(err);
    return NextResponse.json(body, { status });
  }
}

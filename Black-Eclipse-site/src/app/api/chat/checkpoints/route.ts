import { NextResponse } from "next/server";
import { guardExpensiveMutation } from "@/lib/api-guard";
import { SessionError } from "@/lib/chat/session-store";
import {
  createCheckpoint,
  deleteCheckpoint,
  listCheckpoints,
  readCheckpoint,
} from "@/lib/chat/checkpoint-store";

export const dynamic = "force-dynamic";

// /api/chat/checkpoints — restorable snapshots of a conversation.
//
// GET    ?chatId=..            → { checkpoints }
// GET    ?chatId=..&id=..      → { snapshot }   (for restore)
// POST   { chatId, label, messages } → { checkpoint }
// DELETE ?chatId=..&id=..      → { success }
//
// The front door owns the filesystem; the Python runtime stays read-only. Chat
// state itself lives in the browser, so the client sends the snapshot it wants
// saved and restores from the returned payload.

function statusFor(err: unknown): { status: number; body: { error: string; code?: string } } {
  if (err instanceof SessionError) {
    const status = err.code === "CHECKPOINT_TOO_LARGE" ? 413 : 400;
    return { status, body: { error: err.message, code: err.code } };
  }
  console.error("[api/chat/checkpoints] error:", err);
  return { status: 500, body: { error: "Checkpoint operation failed" } };
}

export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const chatId = params.get("chatId") ?? "";
  const id = params.get("id");
  try {
    if (id) {
      const snapshot = await readCheckpoint(chatId, id);
      if (!snapshot) return NextResponse.json({ error: "Checkpoint not found" }, { status: 404 });
      return NextResponse.json({ success: true, snapshot });
    }
    return NextResponse.json({ success: true, checkpoints: await listCheckpoints(chatId) });
  } catch (err) {
    const { status, body } = statusFor(err);
    return NextResponse.json(body, { status });
  }
}

export async function POST(request: Request) {
  const blocked = guardExpensiveMutation(request, "chat-checkpoints", { limit: 120, windowMs: 60_000 });
  if (blocked) {
    return NextResponse.json(blocked.body, { status: blocked.status, headers: blocked.headers });
  }
  try {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const chatId = typeof body.chatId === "string" ? body.chatId : "";
    const label = typeof body.label === "string" ? body.label : "Checkpoint";
    const rawMessages = Array.isArray(body.messages) ? body.messages : [];
    const messages = rawMessages
      .filter(
        (m): m is { id: string; role: string; content: string } =>
          m !== null &&
          typeof m === "object" &&
          typeof (m as { id?: unknown }).id === "string" &&
          typeof (m as { role?: unknown }).role === "string" &&
          typeof (m as { content?: unknown }).content === "string"
      )
      .slice(-200);
    const checkpoint = await createCheckpoint(chatId, label, messages);
    return NextResponse.json({ success: true, checkpoint });
  } catch (err) {
    const { status, body } = statusFor(err);
    return NextResponse.json(body, { status });
  }
}

export async function DELETE(request: Request) {
  const blocked = guardExpensiveMutation(request, "chat-checkpoints", { limit: 120, windowMs: 60_000 });
  if (blocked) {
    return NextResponse.json(blocked.body, { status: blocked.status, headers: blocked.headers });
  }
  try {
    const params = new URL(request.url).searchParams;
    const chatId = params.get("chatId") ?? "";
    const id = params.get("id") ?? "";
    if (!id) return NextResponse.json({ error: "id is required" }, { status: 400 });
    await deleteCheckpoint(chatId, id);
    return NextResponse.json({ success: true });
  } catch (err) {
    const { status, body } = statusFor(err);
    return NextResponse.json(body, { status });
  }
}

import { NextResponse } from "next/server";
import { guardExpensiveMutation } from "@/lib/api-guard";
import {
  SessionError,
  deleteSessionFile,
  getSession,
  writeSessionFile,
} from "@/lib/chat/session-store";
import { SESSION_LIMITS, type SessionFileKind } from "@/lib/chat/session-types";

export const dynamic = "force-dynamic";

// /api/chat/session — the per-conversation workspace folder.
//
// GET  ?chatId=..                            → { session }
// POST { chatId, kind, name, contentBase64 } → { file }
// DELETE ?chatId=..&kind=..&name=..          → { success }
//
// Uploads arrive as JSON with a base64 body rather than multipart so the route
// stays dependency-free and works with the same-origin mutation guard. The
// original bytes are stored (download returns the real file); text extraction
// for agent context happens at run time from those bytes.

function statusFor(err: unknown): { status: number; body: { error: string; code?: string } } {
  if (err instanceof SessionError) {
    const status = err.code === "FILE_TOO_LARGE" || err.code === "TOO_MANY_FILES" ? 413 : 400;
    return { status, body: { error: err.message, code: err.code } };
  }
  console.error("[api/chat/session] error:", err);
  return { status: 500, body: { error: "Session operation failed" } };
}

function parseKind(value: unknown): SessionFileKind | null {
  return value === "context" || value === "output" ? value : null;
}

export async function GET(request: Request) {
  const chatId = new URL(request.url).searchParams.get("chatId") ?? "";
  try {
    const session = await getSession(chatId);
    return NextResponse.json({ success: true, session });
  } catch (err) {
    const { status, body } = statusFor(err);
    return NextResponse.json(body, { status });
  }
}

export async function POST(request: Request) {
  const blocked = guardExpensiveMutation(request, "chat-session", { limit: 120, windowMs: 60_000 });
  if (blocked) {
    return NextResponse.json(blocked.body, { status: blocked.status, headers: blocked.headers });
  }
  try {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const chatId = typeof body.chatId === "string" ? body.chatId : "";
    const kind = parseKind(body.kind);
    const name = typeof body.name === "string" ? body.name : "";
    const contentBase64 = typeof body.contentBase64 === "string" ? body.contentBase64 : "";
    if (!kind) return NextResponse.json({ error: "kind must be 'context' or 'output'" }, { status: 400 });
    if (!name) return NextResponse.json({ error: "name is required" }, { status: 400 });
    if (!contentBase64) return NextResponse.json({ error: "contentBase64 is required" }, { status: 400 });
    const bytes = Buffer.from(contentBase64, "base64");
    if (bytes.byteLength > SESSION_LIMITS.maxFileBytes) {
      return NextResponse.json(
        { error: `File exceeds ${Math.round(SESSION_LIMITS.maxFileBytes / 1024 / 1024)}MB limit` },
        { status: 413 }
      );
    }
    const file = await writeSessionFile(chatId, { name, bytes, kind });
    return NextResponse.json({ success: true, file });
  } catch (err) {
    const { status, body } = statusFor(err);
    return NextResponse.json(body, { status });
  }
}

export async function DELETE(request: Request) {
  const blocked = guardExpensiveMutation(request, "chat-session", { limit: 120, windowMs: 60_000 });
  if (blocked) {
    return NextResponse.json(blocked.body, { status: blocked.status, headers: blocked.headers });
  }
  try {
    const params = new URL(request.url).searchParams;
    const chatId = params.get("chatId") ?? "";
    const kind = parseKind(params.get("kind"));
    const name = params.get("name") ?? "";
    if (!kind) return NextResponse.json({ error: "kind must be 'context' or 'output'" }, { status: 400 });
    if (!name) return NextResponse.json({ error: "name is required" }, { status: 400 });
    await deleteSessionFile(chatId, kind, name);
    return NextResponse.json({ success: true });
  } catch (err) {
    const { status, body } = statusFor(err);
    return NextResponse.json(body, { status });
  }
}

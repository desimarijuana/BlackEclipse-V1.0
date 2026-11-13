import { NextResponse } from "next/server";
import { gzip } from "node:zlib";
import { promisify } from "node:util";
import { guardExpensiveMutation } from "@/lib/api-guard";
import {
  SessionError,
  deleteTranscript,
  listTranscripts,
  readTranscript,
  writeTranscript,
} from "@/lib/chat/session-store";
import { reconcileStuckTranscripts } from "@/lib/chat/transcript-reconcile";

const gzipAsync = promisify(gzip);

export const dynamic = "force-dynamic";

// /api/chat/transcript — server-side conversation transcripts.
//
// The ChatBot tab keeps transcripts in localStorage as an instant cache, but
// localStorage is scoped to the browser ORIGIN: closing the server, switching
// between https://host and http://127.0.0.1:port, or clearing storage silently
// dropped every chat. This route persists a copy on disk beside the session's
// files so a conversation survives all of those.
//
// GET    ?chatId=..                    → { transcript }   (one, or null)
// GET                                  → { conversations } (all, newest first)
// POST   { chatId, transcript }        → { transcript }   (upsert)
// DELETE ?chatId=..                    → { success }

function statusFor(err: unknown): { status: number; body: { error: string; code?: string } } {
  if (err instanceof SessionError) return { status: 400, body: { error: err.message, code: err.code } };
  console.error("[api/chat/transcript] error:", err);
  return { status: 500, body: { error: "Transcript operation failed" } };
}

/**
 * JSON response, gzipped when the client accepts it and the body is large.
 * `next start` applies its built-in compression to pages/static assets but NOT
 * to route-handler responses, and a full transcript list is several MB (every
 * conversation's whole message history), fetched on every app boot. Compressing
 * it here cuts the transfer ~10x; small bodies stay plain. Compression is
 * ASYNC so it never blocks the single-threaded server while other requests wait.
 */
async function jsonResponse(request: Request, data: unknown): Promise<NextResponse> {
  const payload = JSON.stringify(data);
  const accept = request.headers.get("accept-encoding") ?? "";
  if (payload.length > 1024 && /\bgzip\b/.test(accept)) {
    const gz = await gzipAsync(Buffer.from(payload));
    return new NextResponse(new Uint8Array(gz), {
      headers: {
        "content-type": "application/json; charset=utf-8",
        "content-encoding": "gzip",
        vary: "Accept-Encoding",
      },
    });
  }
  return new NextResponse(payload, {
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

export async function GET(request: Request) {
  const chatId = new URL(request.url).searchParams.get("chatId") ?? "";
  try {
    if (chatId) {
      return await jsonResponse(request, { success: true, transcript: await readTranscript(chatId) });
    }
    const conversations = await listTranscripts();
    // Self-heal: a conversation left with an empty "queued" placeholder (tab
    // reload / app restart mid-run) is filled from its completed run's stored
    // output. Bounded and throttled; a failure returns the list untouched.
    let healed = conversations;
    try {
      healed = await reconcileStuckTranscripts(conversations);
    } catch (err) {
      console.error("[api/chat/transcript] reconcile skipped:", err);
    }
    return await jsonResponse(request, { success: true, conversations: healed });
  } catch (err) {
    const { status, body } = statusFor(err);
    return NextResponse.json(body, { status });
  }
}

export async function POST(request: Request) {
  const blocked = guardExpensiveMutation(request, "chat-transcript", { limit: 240, windowMs: 60_000 });
  if (blocked) {
    return NextResponse.json(blocked.body, { status: blocked.status, headers: blocked.headers });
  }
  try {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const chatId = typeof body.chatId === "string" ? body.chatId : "";
    const transcript = body.transcript;
    if (!chatId) return NextResponse.json({ error: "chatId is required" }, { status: 400 });
    if (transcript === null || typeof transcript !== "object" || Array.isArray(transcript)) {
      return NextResponse.json({ error: "transcript must be an object" }, { status: 400 });
    }
    const stored = await writeTranscript(chatId, transcript as Parameters<typeof writeTranscript>[1]);
    return NextResponse.json({ success: true, transcript: stored });
  } catch (err) {
    const { status, body } = statusFor(err);
    return NextResponse.json(body, { status });
  }
}

export async function DELETE(request: Request) {
  const blocked = guardExpensiveMutation(request, "chat-transcript", { limit: 240, windowMs: 60_000 });
  if (blocked) {
    return NextResponse.json(blocked.body, { status: blocked.status, headers: blocked.headers });
  }
  try {
    const chatId = new URL(request.url).searchParams.get("chatId") ?? "";
    if (!chatId) return NextResponse.json({ error: "chatId is required" }, { status: 400 });
    await deleteTranscript(chatId);
    return NextResponse.json({ success: true });
  } catch (err) {
    const { status, body } = statusFor(err);
    return NextResponse.json(body, { status });
  }
}

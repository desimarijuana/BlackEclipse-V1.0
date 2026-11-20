import { NextResponse } from "next/server";
import { guardExpensiveMutation } from "@/lib/api-guard";
import {
  SessionError,
  deleteTranscript,
  listTranscripts,
  readTranscript,
  summarizeTranscript,
  writeTranscript,
} from "@/lib/chat/session-store";
import { reconcileStuckTranscripts } from "@/lib/chat/transcript-reconcile";

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
 * JSON response. This used to gzip large bodies by hand, but the Turbopack
 * production build (and therefore the shipped app) served those bytes with the
 * `content-encoding` header dropped — the browser then tried to parse raw gzip
 * as JSON and the whole transcript hydration failed silently. The boot payload
 * is now metadata-only (~50 KB plain), so let the transport handle any
 * compression and keep the body parseable by definition.
 */
function jsonResponse(data: unknown): NextResponse {
  return new NextResponse(JSON.stringify(data), {
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const chatId = params.get("chatId") ?? "";
  // `?summary=1` is the boot-time list: metadata for every conversation, no
  // message bodies. The full list is the whole chat history (16 MB measured),
  // so fetching it on every open blocked the server and the UI. A message body
  // is fetched per conversation with `?chatId=…` when it is actually opened.
  const summary = params.get("summary") === "1";
  try {
    if (chatId) {
      return jsonResponse({ success: true, transcript: await readTranscript(chatId) });
    }
    const conversations = await listTranscripts();
    // Self-heal: a conversation left with an empty "queued" placeholder (tab
    // reload / app restart mid-run) is filled from its completed run's stored
    // output. Bounded and throttled; a failure returns the list untouched.
    //
    // The BOOT list must not wait for it: when the runtime is down the heal
    // call sits on the runtime timeout (measured 48 s) and the whole app sat
    // behind it. The summary carries no message bodies anyway, so heal after
    // responding and let the next read (or the hydrated conversation) see the
    // repaired file.
    if (summary) {
      void reconcileStuckTranscripts(conversations).catch((err) =>
        console.error("[api/chat/transcript] reconcile skipped:", err),
      );
      return jsonResponse({
        success: true,
        conversations: conversations.map(summarizeTranscript),
      });
    }
    let healed = conversations;
    try {
      healed = await reconcileStuckTranscripts(conversations);
    } catch (err) {
      console.error("[api/chat/transcript] reconcile skipped:", err);
    }
    return jsonResponse({ success: true, conversations: healed });
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

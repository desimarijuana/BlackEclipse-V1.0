import { NextResponse } from "next/server";
import { guardExpensiveMutation } from "@/lib/api-guard";
import { readNotebook, writeNotebook } from "@/lib/chat/notebook-store";

export const dynamic = "force-dynamic";

// /api/chat/notebook — the per-conversation notebook document.
//
// GET  ?chatId=..            → { success, notebook }
// POST { chatId, cells }     → { success, notebook }   (whole-document upsert)
//
// The cells are an EDITABLE working document, not the transcript. The route
// validates the chat id through the session store's own guard and bounds the
// document before writing it.

function chatIdFrom(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function validChatId(chatId: string): boolean {
  return /^[A-Za-z0-9_-]{1,64}$/.test(chatId);
}

export async function GET(request: Request) {
  const chatId = new URL(request.url).searchParams.get("chatId") ?? "";
  if (!validChatId(chatId)) return NextResponse.json({ error: "a valid chatId is required" }, { status: 400 });
  try {
    return NextResponse.json({ success: true, notebook: await readNotebook(chatId) });
  } catch (err) {
    console.error("[api/chat/notebook] GET error:", err);
    return NextResponse.json({ error: "Notebook could not be read" }, { status: 400 });
  }
}

export async function POST(request: Request) {
  const blocked = guardExpensiveMutation(request, "chat-notebook", { limit: 240, windowMs: 60_000 });
  if (blocked) {
    return NextResponse.json(blocked.body, { status: blocked.status, headers: blocked.headers });
  }
  try {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const chatId = chatIdFrom(body.chatId);
    if (!validChatId(chatId)) return NextResponse.json({ error: "a valid chatId is required" }, { status: 400 });
    const notebook = await writeNotebook(chatId, body.cells);
    return NextResponse.json({ success: true, notebook });
  } catch (err) {
    console.error("[api/chat/notebook] POST error:", err);
    const message = err instanceof Error ? err.message : "Notebook could not be saved";
    return NextResponse.json({ error: message }, { status: 400 });
  }
}

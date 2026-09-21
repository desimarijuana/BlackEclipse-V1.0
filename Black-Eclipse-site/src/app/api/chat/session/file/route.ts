import { NextResponse } from "next/server";
import { SessionError, readSessionFile } from "@/lib/chat/session-store";
import type { SessionFileKind } from "@/lib/chat/session-types";

export const dynamic = "force-dynamic";

// GET /api/chat/session/file?chatId=..&kind=..&name=.. — download one session
// file. A separate route from the session listing so the listing stays cheap
// and a large file is only read when actually requested.
export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const chatId = params.get("chatId") ?? "";
  const kind = params.get("kind");
  const name = params.get("name") ?? "";
  if (kind !== "context" && kind !== "output") {
    return NextResponse.json({ error: "kind must be 'context' or 'output'" }, { status: 400 });
  }
  if (!name) return NextResponse.json({ error: "name is required" }, { status: 400 });

  try {
    const bytes = await readSessionFile(chatId, kind as SessionFileKind, name);
    return new NextResponse(new Uint8Array(bytes), {
      headers: {
        "Content-Type": "application/octet-stream",
        "Content-Disposition": `attachment; filename="${encodeURIComponent(name)}"`,
        "Content-Length": String(bytes.byteLength),
      },
    });
  } catch (err) {
    if (err instanceof SessionError) {
      const status = err.code === "INVALID_FILE_NAME" || err.code === "INVALID_CHAT_ID" ? 400 : 404;
      return NextResponse.json({ error: err.message }, { status });
    }
    console.error("[api/chat/session/file] error:", err);
    return NextResponse.json({ error: "Failed to read file" }, { status: 500 });
  }
}

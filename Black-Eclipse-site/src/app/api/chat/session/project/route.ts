import { NextResponse } from "next/server";

import { getWorkspaceRoots, listTrustedRoots } from "@/lib/harness/code-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";
import {
  readSessionProject,
  writeSessionProject,
} from "@/lib/chat/session-store";

export const dynamic = "force-dynamic";

// /api/chat/session/project — the project folder bound to ONE conversation.
//
// GET  ?chatId=..            → { project, roots, runtime }
// POST { chatId, rootId }    → { project }   (rootId: null clears the binding)
//
// The client sends an approved ROOT ID, never a path. The run route reads this
// binding and forwards the id to the runtime, which resolves it against
// TrustedRoot — so a chat can only point at a folder a person approved.

const CHAT_ID_RE = /^[A-Za-z0-9_-]{1,64}$/;

function bad(message: string, status = 400) {
  return NextResponse.json({ error: message }, { status });
}

export async function GET(request: Request) {
  const chatId = new URL(request.url).searchParams.get("chatId") ?? "";
  if (!CHAT_ID_RE.test(chatId)) return bad("a valid chatId is required");

  const project = await readSessionProject(chatId);
  let roots: Awaited<ReturnType<typeof listTrustedRoots>> = [];
  let defaultRoot: string | null = null;
  let runtime = "ready";
  try {
    const workspace = await getWorkspaceRoots();
    roots = workspace.roots;
    defaultRoot = workspace.defaultRoot;
  } catch (err) {
    // The binding is still readable; only the folder list is unavailable.
    runtime = err instanceof HarnessRuntimeUnavailable ? "unavailable" : "error";
  }
  return NextResponse.json({ success: true, project, roots, runtime, defaultRoot });
}

export async function POST(request: Request) {
  const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
  const chatId = typeof body.chatId === "string" ? body.chatId : "";
  if (!CHAT_ID_RE.test(chatId)) return bad("a valid chatId is required");

  const rawRootId = body.rootId;
  const rootId = typeof rawRootId === "string" && rawRootId.trim() ? rawRootId.trim() : null;

  if (rootId === null) {
    // Clearing needs no runtime: it only removes the binding.
    const project = await writeSessionProject(chatId, { workspaceRootId: null, workspacePath: null });
    return NextResponse.json({ success: true, project });
  }

  // Only an APPROVED root may be bound. The check happens here (server-side),
  // and again in the runtime when the run resolves the id.
  let roots: Awaited<ReturnType<typeof listTrustedRoots>>;
  try {
    roots = await listTrustedRoots();
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return bad(
      unavailable ? "The Eclipse runtime is not available right now." : "Could not check approved folders.",
      unavailable ? 503 : 500,
    );
  }
  const root = roots.find((item) => item.id === rootId);
  if (!root) return bad("That folder is not approved for Eclipse.", 404);

  const project = await writeSessionProject(chatId, {
    workspaceRootId: root.id,
    workspacePath: root.path,
  });
  return NextResponse.json({ success: true, project });
}

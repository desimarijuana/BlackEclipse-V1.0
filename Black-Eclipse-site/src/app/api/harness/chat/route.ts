import { NextResponse } from "next/server";
import { guardExpensiveMutation } from "@/lib/api-guard";
import { chatWithAgent, HarnessError, HarnessRuntimeUnavailable, toHarnessErrorJson } from "@/lib/harness";
import { runtimeIdentityHeaders } from "@/lib/harness/runtime-identity";
import { loadContextDocuments, writeSessionFile } from "@/lib/chat/session-store";
import { isReasoningLevel } from "@/lib/agent/reasoning";
import { parseCommandInvocation } from "@/lib/harness/command-parser";
import { executeCommandFromText, isRoutedCommand } from "@/lib/harness/command-router";
import { isOperatorRequest } from "@/lib/harness/skills-client";
import { newRunId } from "@/lib/harness/ids";

export const dynamic = "force-dynamic";
export const maxDuration = 180;

// POST /api/harness/chat — the chat surfaces' entry point to the Eclipse Agent.
// Body: { query, history?, chatId? }
//
// Same harness runtime as /api/harness/runs (prompt + tools + persistence), but
// shaped for conversation: it returns the agent's final text directly and has a
// chat-appropriate rate limit rather than the run limit.
//
// When `chatId` is present, the conversation's workspace folder supplies context
// documents (extracted text, injected into the run) and receives the agent's
// final answer as an output file. The Python runtime stays read-only; all
// filesystem work happens here, on the front door.
export async function POST(request: Request) {
  const blocked = guardExpensiveMutation(request, "harness-chat", { limit: 60, windowMs: 5 * 60_000 });
  if (blocked) {
    return NextResponse.json(blocked.body, { status: blocked.status, headers: blocked.headers });
  }
  try {
    const body = await request.json().catch(() => ({}));
    const query = typeof (body as Record<string, unknown>).query === "string"
      ? ((body as Record<string, unknown>).query as string).trim()
      : "";
    if (!query) {
      return NextResponse.json({ error: "query is required" }, { status: 400 });
    }
    if (query.length > 4000) {
      return NextResponse.json({ error: "query too long (max 4000 chars)" }, { status: 400 });
    }

    // A routed slash command (`/skills`, `/skill`, `/status`, …) is executed by the
    // shared command router. Profile commands (`/eclipsesdk`) and ordinary prose
    // fall through to the normal agent path; an unknown `/token` falls through too.
    const commandInvocation = parseCommandInvocation(query);
    if (commandInvocation?.spec && isRoutedCommand(commandInvocation.spec)) {
      const cmdResult = await executeCommandFromText(query, {
        operator: isOperatorRequest(request),
        origin: new URL(request.url).origin,
      });
      if (cmdResult) {
        return NextResponse.json({
          success: cmdResult.ok,
          content: cmdResult.output,
          runId: newRunId(),
          command: cmdResult.command,
          documentsUsed: [],
        });
      }
    }

    const rawHistory = (body as Record<string, unknown>).history;
    const history = Array.isArray(rawHistory)
      ? rawHistory
          .filter(
            (t): t is { role: "user" | "assistant"; content: string } =>
              t !== null &&
              typeof t === "object" &&
              ((t as { role?: unknown }).role === "user" || (t as { role?: unknown }).role === "assistant") &&
              typeof (t as { content?: unknown }).content === "string"
          )
          .map((t) => ({ role: t.role, content: t.content }))
      : [];

    const chatId = typeof (body as Record<string, unknown>).chatId === "string"
      ? ((body as Record<string, unknown>).chatId as string)
      : "";
    // Bot chats and group-member turns opt into private per-conversation memory.
    const memoryScope = (body as Record<string, unknown>).memoryScope === "conversation"
      ? ("conversation" as const)
      : undefined;
    const model = typeof (body as Record<string, unknown>).model === "string"
      ? ((body as Record<string, unknown>).model as string).trim()
      : "";
    // Per-question reasoning-effort override ("model intelligence"). Only a
    // value from the shared vocabulary is honoured; anything else is ignored so
    // the runtime falls back to the saved default / task profile.
    const rawEffort = (body as Record<string, unknown>).reasoningEffort;
    const reasoningEffort = isReasoningLevel(rawEffort) ? rawEffort : undefined;
    // Client-supplied run id so cancellation is possible mid-run; ignored when
    // absent, in which case the server mints one.
    const rawRunId = (body as Record<string, unknown>).runId;
    const runId = typeof rawRunId === "string" && /^run_[A-Za-z0-9-]{1,64}$/.test(rawRunId)
      ? rawRunId
      : undefined;

    // Documents live in the conversation's session folder and are extracted
    // here — never handed to the read-only runtime as files.
    let documents: Array<{ name: string; text: string }> = [];
    if (chatId) {
      try {
        documents = await loadContextDocuments(chatId);
      } catch (err) {
        console.warn("[api/harness/chat] could not load context documents:", err);
      }
    }

    const uiContext = (() => {
      const raw = (body as Record<string, unknown>).uiContext;
      if (raw === null || typeof raw !== "object" || Array.isArray(raw)) return undefined;
      const page = (raw as { page?: unknown }).page;
      if (page === null || typeof page !== "object" || Array.isArray(page)) return undefined;
      const p = page as Record<string, unknown>;
      const str = (v: unknown) => (typeof v === "string" ? v.trim().slice(0, 200) : undefined);
      const out = { blueprintId: str(p.blueprintId), title: str(p.title), path: str(p.path) };
      if (!out.blueprintId && !out.title && !out.path) return undefined;
      return { page: out };
    })();

    // The project this turn is scoped to. The runtime resolves the id and puts
    // the project's members in front of the model as a per-run context note; an
    // unknown id is reported by the runtime, never silently ignored.
    const rawProjectId = (body as Record<string, unknown>).projectId;
    const projectId = typeof rawProjectId === "string" && /^[A-Za-z0-9_-]{1,64}$/.test(rawProjectId.trim())
      ? rawProjectId.trim()
      : undefined;

    const identityHeaders = await runtimeIdentityHeaders(request);
    const result = await chatWithAgent(query, history, documents, runId, chatId || undefined, model || undefined, reasoningEffort, identityHeaders, uiContext, memoryScope, projectId);
    if (result.status === "failed") {
      return NextResponse.json(
        { success: false, error: result.error, runId: result.runId },
        { status: 502 }
      );
    }

    // Persist the agent's answer into the session folder so it is a durable
    // output, not just a bubble. Best-effort: a failure here must not fail the
    // chat, and the output is never fabricated if the write fails.
    if (chatId && result.output) {
      try {
        const stamp = new Date().toISOString().replace(/[:.]/g, "-");
        await writeSessionFile(chatId, {
          name: `answer-${stamp}.md`,
          bytes: Buffer.from(result.output, "utf8"),
          kind: "output",
        });
      } catch (err) {
        console.warn("[api/harness/chat] could not save output to session folder:", err);
      }
    }

    return NextResponse.json({
      success: true,
      content: result.output,
      runId: result.runId,
      documentsUsed: documents.map((d) => d.name),
    });
  } catch (err) {
    const error = toHarnessErrorJson(err);
    const status =
      err instanceof HarnessRuntimeUnavailable ? 503
      : err instanceof HarnessError && err.code === "PROVIDER_NOT_CONFIGURED" ? 503
      : err instanceof HarnessError && err.code === "INVALID_INPUT" ? 400
      : 500;
    console.error("[api/harness/chat] POST error:", error.message);
    return NextResponse.json({ error: error.message, code: error.code }, { status });
  }
}

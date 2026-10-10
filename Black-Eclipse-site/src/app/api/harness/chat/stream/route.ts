import { guardExpensiveMutation } from "@/lib/api-guard";
import {
  startChatRun,
  getRunFromRuntime,
  HarnessError,
  HarnessRuntimeUnavailable,
  toHarnessErrorJson,
} from "@/lib/harness";
import { HARNESS_PY_URL } from "@/lib/harness/python-runtime";
import { runtimeIdentityHeaders } from "@/lib/harness/runtime-identity";
import { loadContextDocuments, writeSessionFile } from "@/lib/chat/session-store";
import { isReasoningLevel } from "@/lib/agent/reasoning";

export const dynamic = "force-dynamic";
export const maxDuration = 300;

// POST /api/harness/chat/stream — streaming chat.
//
// Starts the run in the background, then relays the runtime's SSE stream to the
// browser (run.started, model.delta tokens, tool.*, run.completed). When the run
// finishes, the final answer is persisted to the session folder exactly like the
// non-streaming route. Body: { query, history?, chatId?, runId? }
export async function POST(request: Request) {
  const blocked = guardExpensiveMutation(request, "harness-chat-stream", { limit: 60, windowMs: 5 * 60_000 });
  if (blocked) {
    return Response.json(blocked.body, { status: blocked.status, headers: blocked.headers });
  }

  let body: Record<string, unknown>;
  try {
    body = (await request.json()) as Record<string, unknown>;
  } catch {
    return Response.json({ error: "invalid JSON body" }, { status: 400 });
  }

  const query = typeof body.query === "string" ? body.query.trim() : "";
  if (!query) return Response.json({ error: "query is required" }, { status: 400 });
  if (query.length > 4000) return Response.json({ error: "query too long (max 4000 chars)" }, { status: 400 });

  const rawHistory = body.history;
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

  const chatId = typeof body.chatId === "string" ? body.chatId : "";
  const model = typeof body.model === "string" ? body.model.trim() : "";
  const rawEffort = body.reasoningEffort;
  const reasoningEffort = isReasoningLevel(rawEffort) ? rawEffort : undefined;
  const rawRunId = body.runId;
  const runId =
    typeof rawRunId === "string" && /^run_[A-Za-z0-9-]{1,64}$/.test(rawRunId) ? rawRunId : undefined;

  // Presentation-only UI focus (which page the user is on). Sanitized + bounded:
  // strings only, trimmed, capped; anything else is dropped.
  const uiContext = (() => {
    const raw = body.uiContext;
    if (raw === null || typeof raw !== "object" || Array.isArray(raw)) return undefined;
    const page = (raw as { page?: unknown }).page;
    if (page === null || typeof page !== "object" || Array.isArray(page)) return undefined;
    const p = page as Record<string, unknown>;
    const str = (v: unknown) => (typeof v === "string" ? v.trim().slice(0, 200) : undefined);
    const out = { blueprintId: str(p.blueprintId), title: str(p.title), path: str(p.path) };
    if (!out.blueprintId && !out.title && !out.path) return undefined;
    return { page: out };
  })();

  let documents: Array<{ name: string; text: string }> = [];
  if (chatId) {
    try {
      documents = await loadContextDocuments(chatId);
    } catch (err) {
      console.warn("[api/harness/chat/stream] could not load context documents:", err);
    }
  }

  let id: string;
  try {
    const identityHeaders = await runtimeIdentityHeaders(request);
    id = await startChatRun(query, history, documents, runId, chatId || undefined, model || undefined, reasoningEffort, identityHeaders, uiContext);
  } catch (err) {
    const error = toHarnessErrorJson(err);
    const status =
      err instanceof HarnessRuntimeUnavailable ? 503
      : err instanceof HarnessError && err.code === "PROVIDER_NOT_CONFIGURED" ? 503
      : err instanceof HarnessError && err.code === "INVALID_INPUT" ? 400
      : 500;
    return Response.json({ error: error.message, code: error.code }, { status });
  }

  // Relay the runtime stream and capture the final answer to persist on close.
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      const send = (type: string, data: unknown) => {
        controller.enqueue(encoder.encode(`event: ${type}\ndata: ${JSON.stringify(data)}\n\n`));
      };
      send("client.run", { runId: id, documentsUsed: documents.map((d) => d.name) });

      let finished = false;
      try {
        // Talk to the runtime directly: a relative fetch has no base URL on the
        // server. The runtime owns the event bus; this relays its frames.
        const upstream = await fetch(`${HARNESS_PY_URL}/runs/${encodeURIComponent(id)}/stream`, {
          headers: { Accept: "text/event-stream" },
        });
        if (upstream.ok && upstream.body) {
          const reader = upstream.body.getReader();
          const decoder = new TextDecoder();
          let buffer = "";
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const text = decoder.decode(value, { stream: true });
            controller.enqueue(encoder.encode(text));
            buffer += text;
            if (buffer.includes("event: run.completed") || buffer.includes("event: run.failed")) {
              finished = true;
            }
          }
        }
      } catch (err) {
        send("client.error", { message: err instanceof Error ? err.message : String(err) });
      }

      // Fetch the terminal result so the answer bubble has the final text.
      try {
        const run = await getRunFromRuntime(id);
        if (run) {
          send("client.final", {
            runId: id,
            status: run.status,
            output: run.output,
            error: run.error,
            provider: run.provider ?? null,
            model: run.model ?? null,
            research: run.research ?? null,
            memory: run.memory ?? null,
            context: run.context ?? null,
            codeVerification: run.codeVerification ?? null,
            autonomy: run.autonomy ?? null,
            workspaceId: run.workspaceId ?? null,
            capability: run.capability ?? null,
            vision: run.vision ?? null,
            documents: run.documents ?? null,
          });
          if (chatId && run.output && run.status === "completed") {
            const stamp = new Date().toISOString().replace(/[:.]/g, "-");
            await writeSessionFile(chatId, {
              name: `answer-${stamp}.md`,
              bytes: Buffer.from(run.output, "utf8"),
              kind: "output",
            }).catch(() => undefined);
          }
        } else if (!finished) {
          send("client.error", { message: "run not found after stream ended" });
        }
      } catch (err) {
        send("client.error", { message: err instanceof Error ? err.message : String(err) });
      } finally {
        send("stream.end", {});
        controller.close();
      }
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}

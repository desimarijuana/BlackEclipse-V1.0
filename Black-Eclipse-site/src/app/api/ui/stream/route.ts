// ─── UI blueprint change stream (SSE) ────────────────────────────────────────
// A lightweight Server-Sent-Events stream that tells the browser when the
// durable UI blueprints change, so the Pages surface can reload the open page
// the moment an agent (or another tab) edits it — instead of polling blindly.
//
// It adds NO UI state: it only compares the runtime's most-recently-updated
// blueprint (id:revision:updatedAt) on a short cadence and emits a `changed`
// event when that tuple moves. The client then does the (cheap, revision-diffed)
// reload. If the runtime is unavailable the stream stays open and reports it.

import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const POLL_MS = 4_000;
const HEARTBEAT_MS = 15_000;

interface ChangeMarker {
  key: string;
  blueprintId: string;
  revision: number;
  path: string | null;
  kind: "dashboard" | "ui";
}

async function latestMarker(): Promise<ChangeMarker | null> {
  const token = runtimeCallbackToken();
  const res = await fetch(`${HARNESS_PY_URL}/ui/blueprints?limit=1`, {
    headers: token ? { "X-Harness-Operator": token } : {},
    signal: AbortSignal.timeout(5_000),
    cache: "no-store",
  });
  if (!res.ok) return null;
  const body = (await res.json().catch(() => null)) as
    | { blueprints?: Array<{ id: string; revision: number; updatedAt: string; path?: string | null }> }
    | null;
  const b = body?.blueprints?.[0];
  if (!b) return null;
  const path = b.path ?? null;
  return {
    key: `${b.id}:${b.revision}:${b.updatedAt}`,
    blueprintId: b.id,
    revision: b.revision,
    path,
    kind: path?.toLowerCase().startsWith("/dashboard/") ? "dashboard" : "ui",
  };
}

export async function GET(request: Request): Promise<Response> {
  const encoder = new TextEncoder();
  let poll: ReturnType<typeof setInterval> | null = null;
  let beat: ReturnType<typeof setInterval> | null = null;
  let closed = false;
  let last: string | null = null;

  const stop = () => {
    closed = true;
    if (poll) clearInterval(poll);
    if (beat) clearInterval(beat);
    poll = beat = null;
  };

  const stream = new ReadableStream({
    async start(controller) {
      const send = (event: string, data: unknown) => {
        if (closed) return;
        try {
          controller.enqueue(encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`));
        } catch {
          stop();
        }
      };

      const tick = async () => {
        if (closed) return;
        try {
          if (!(await ensurePythonRuntime())) {
            send("error", { error: "runtime unavailable" });
            return;
          }
          const marker = await latestMarker();
          if (marker && marker.key !== last) {
            last = marker.key;
            send("changed", {
              at: Date.now(),
              kind: marker.kind,
              blueprintId: marker.blueprintId,
              revision: marker.revision,
              path: marker.path,
            });
          }
        } catch {
          /* transient — try again next tick */
        }
      };

      controller.enqueue(encoder.encode(": connected\n\n"));
      // Don't block the connection on the first runtime probe.
      void tick();
      poll = setInterval(() => void tick(), POLL_MS);
      beat = setInterval(() => {
        if (closed) return;
        try {
          controller.enqueue(encoder.encode(": ping\n\n"));
        } catch {
          stop();
        }
      }, HEARTBEAT_MS);

      request.signal.addEventListener("abort", () => {
        stop();
        try {
          controller.close();
        } catch {
          /* already closed */
        }
      });
    },
    cancel() {
      stop();
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}

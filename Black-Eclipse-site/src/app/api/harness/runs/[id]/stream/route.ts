import { guardMutation } from "@/lib/api-guard";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";

export const dynamic = "force-dynamic";
export const maxDuration = 300;

// GET /api/harness/runs/:id/stream — SSE proxy to the Python runtime.
//
// The runtime owns the event bus; this route only relays its SSE frames to the
// browser (no buffering, no re-shaping). The browser cannot reach 127.0.0.1:8765
// directly, so the front door is the transport.
export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const blocked = guardMutation(request, "harness-stream");
  if (blocked) return new Response(JSON.stringify(blocked.body), { status: blocked.status });

  const { id } = await params;
  if (!id) return new Response("run id required", { status: 400 });

  if (!(await ensurePythonRuntime())) {
    return new Response("runtime unavailable", { status: 503 });
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${HARNESS_PY_URL}/runs/${encodeURIComponent(id)}/stream`, {
      headers: { Accept: "text/event-stream" },
      signal: request.signal,
    });
  } catch {
    return new Response("runtime unavailable", { status: 503 });
  }
  if (!upstream.ok || !upstream.body) {
    return new Response("stream unavailable", { status: upstream.status || 502 });
  }

  return new Response(upstream.body, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}

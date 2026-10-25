// ── /api/graph-runs/[runId]/stream — SSE proxy to the Python runtime ────────
// The runtime owns the graph event log; this route only relays its SSE frames.
// The browser cannot reach the loopback runtime directly, so the front door is
// the transport. No buffering, no re-shaping.

import { HARNESS_PY_URL, ensurePythonRuntime } from '@/lib/harness/python-runtime';
import { runtimeCallbackToken } from '@/lib/harness/runtime-auth';
import { runtimeIdentityHeaders } from '@/lib/harness/runtime-identity';

export const dynamic = 'force-dynamic';
export const maxDuration = 300;

type Ctx = { params: Promise<{ runId: string }> };

export async function GET(request: Request, ctx: Ctx) {
  const { runId } = await ctx.params;
  if (!runId) return new Response('run id required', { status: 400 });
  if (!(await ensurePythonRuntime())) {
    return new Response('runtime unavailable', { status: 503 });
  }

  const token = runtimeCallbackToken();
  const lastEventId = request.headers.get('last-event-id');
  let upstream: Response;
  try {
    upstream = await fetch(`${HARNESS_PY_URL}/graphs/runs/${encodeURIComponent(runId)}/stream`, {
      headers: {
        Accept: 'text/event-stream',
        ...(token ? { 'X-Harness-Operator': token } : {}),
        ...(lastEventId ? { 'Last-Event-ID': lastEventId } : {}),
        ...(await runtimeIdentityHeaders(request)),
      },
      signal: request.signal,
    });
  } catch {
    return new Response('runtime unavailable', { status: 503 });
  }
  if (!upstream.ok || !upstream.body) {
    return new Response('stream unavailable', { status: upstream.status || 502 });
  }

  return new Response(upstream.body, {
    headers: {
      'Content-Type': 'text/event-stream; charset=utf-8',
      'Cache-Control': 'no-cache, no-transform',
      Connection: 'keep-alive',
      'X-Accel-Buffering': 'no',
    },
  });
}

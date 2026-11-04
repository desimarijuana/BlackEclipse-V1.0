import { NextResponse } from "next/server";
import { getLLMConfig } from "@/lib/settings";
import { isLocalBaseUrl } from "@/lib/agent/presets";
import { assertModelAllowed } from "@/lib/privacy";
import { guardMutation } from "@/lib/api-guard";

export const dynamic = "force-dynamic";
export const maxDuration = 30;

// POST /api/agent/test — make a real, cheap request against the configured LLM
// endpoint and report the real result. Honesty rule: never report success from
// the mere presence of a key; only a 2xx from the endpoint counts.
//
// Optional body `{ baseUrl?, apiKey?, model? }` tests an in-progress config
// before it is saved. When omitted, the saved config is used.
export async function POST(request: Request) {
  const blocked = guardMutation(request, "agent-test");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });

  try {
    const body = await request.json().catch(() => ({}));
    const saved = await getLLMConfig();

    const baseUrl = (typeof body.baseUrl === "string" && body.baseUrl ? body.baseUrl : saved.baseUrl).replace(/\/$/, "");
    const model = typeof body.model === "string" && body.model ? body.model : saved.model;
    // A blank incoming key means "use the stored one" (consistent with save).
    const apiKey = typeof body.apiKey === "string" && body.apiKey ? body.apiKey : saved.apiKey;
    const local = isLocalBaseUrl(baseUrl);

    // Local-only mode forbids even a connectivity probe to a remote endpoint.
    try {
      assertModelAllowed(baseUrl, saved.provider);
    } catch (err) {
      return NextResponse.json(
        { ok: false, message: err instanceof Error ? err.message : String(err) },
        { status: 403 },
      );
    }

    if (!apiKey && !local) {
      return NextResponse.json(
        { ok: false, message: "No API key configured for a remote endpoint." },
        { status: 200 }
      );
    }

    const started = Date.now();
    const res = await fetch(`${baseUrl}/models`, {
      method: "GET",
      headers: apiKey ? { Authorization: `Bearer ${apiKey}` } : {},
      signal: AbortSignal.timeout(12000),
    });
    const latencyMs = Date.now() - started;

    if (res.ok) {
      return NextResponse.json({ ok: true, message: `Endpoint reachable · model ${model}`, latencyMs });
    }
    // Anthropic's gateway and some OpenAI-compatible servers don't expose
    // /models. A 404/405 means the host is reachable but does not list models;
    // treat that as reachable-but-unverified rather than a hard failure.
    if (res.status === 404 || res.status === 405) {
      return NextResponse.json({
        ok: true,
        message: `Endpoint reachable (no model list; HTTP ${res.status})`,
        httpStatus: res.status,
        latencyMs,
      });
    }
    return NextResponse.json({
      ok: false,
      message: `Endpoint rejected the request (HTTP ${res.status})`,
      httpStatus: res.status,
      latencyMs,
    });
  } catch (err) {
    return NextResponse.json({
      ok: false,
      message: err instanceof Error ? `Could not reach endpoint: ${err.message}` : "Test failed",
    });
  }
}

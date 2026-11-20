import { NextResponse } from "next/server";
import { getLLMConfig } from "@/lib/settings";
import { resolveLLMProviderId } from "@/lib/agent/presets";
import { testConnection } from "@/lib/agent/connection";
import { guardMutation } from "@/lib/api-guard";

export const dynamic = "force-dynamic";
export const maxDuration = 30;

// POST /api/agent/test — make a real, cheap request against the configured LLM
// endpoint and report the real result. Honesty rule: never report success from
// the mere presence of a key; only a successful probe counts.
//
// The probe is auth-aware and protocol-aware (see `lib/agent/connection`):
// OpenAI-compatible providers get a Bearer request, Anthropic gets `x-api-key`,
// Gemini gets `x-goog-api-key`. This is what stops a valid Claude/Gemini key
// from being reported as "rejected".
//
// Optional body `{ providerId?, baseUrl?, apiKey?, model?, verifyChat? }` tests
// an in-progress config before it is saved. When omitted, the saved config is
// used.
export async function POST(request: Request) {
  const blocked = guardMutation(request, "agent-test");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });

  try {
    const body = await request.json().catch(() => ({}));
    const saved = await getLLMConfig();

    const providerId =
      typeof body.providerId === "string" && body.providerId
        ? body.providerId
        : resolveLLMProviderId(saved);

    const result = await testConnection({
      providerId,
      baseUrl: typeof body.baseUrl === "string" && body.baseUrl ? body.baseUrl : saved.baseUrl,
      model: typeof body.model === "string" && body.model ? body.model : saved.model,
      apiKey: typeof body.apiKey === "string" && body.apiKey ? body.apiKey : saved.apiKey,
      verifyChat: body.verifyChat !== false,
    });

    return NextResponse.json({
      ok: result.ok,
      message: result.message,
      models: result.models,
      latencyMs: result.latencyMs,
      httpStatus: result.httpStatus,
      ...(result.ok ? {} : { code: result.code, error: result.message, detail: result.detail }),
    });
  } catch (err) {
    return NextResponse.json({
      ok: false,
      message: err instanceof Error ? `Could not test the endpoint: ${err.message}` : "Test failed",
      models: [],
    });
  }
}

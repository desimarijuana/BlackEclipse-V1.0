import { NextResponse } from "next/server";
import { guardMutation, rateLimit } from "@/lib/api-guard";
import { getLLMConfig } from "@/lib/settings";
import { getProvider, normalizeApiKey } from "@/lib/providers/registry";
import { resolveProviderKey } from "@/lib/provider-keys";
import { testConnection } from "@/lib/agent/connection";
import { customConnectionKeyEnvVar } from "@/lib/agent/custom-key";

export const dynamic = "force-dynamic";
export const maxDuration = 30;

/**
 * POST /api/llm/test — probe a draft or saved connection with the provider's
 * REAL auth method, then make one tiny chat request. Nothing is persisted.
 *
 * Body: { providerId?, baseUrl?, model?, apiKey?, verifyChat? }
 * A blank apiKey means "use the stored key for this provider".
 */
export async function POST(request: Request) {
  const blocked = guardMutation(request, "llm-test");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });

  const limited = rateLimit("llm-test", { limit: 20, windowMs: 60_000 });
  if (!limited.ok) {
    return NextResponse.json(
      { ok: false, code: "RATE_LIMITED", message: `Too many tests — retry in ${limited.retryAfterSec}s.`, models: [] },
      { status: 429 },
    );
  }

  const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
  const saved = await getLLMConfig();

  const explicitConnectionId =
    typeof body.connectionId === "string" && body.connectionId ? body.connectionId : undefined;
  const providerId =
    typeof body.providerId === "string" && body.providerId
      ? body.providerId
      : explicitConnectionId
        ? "custom"
        : saved.provider;
  const baseUrl =
    typeof body.baseUrl === "string" && body.baseUrl ? body.baseUrl : saved.baseUrl;
  const model = typeof body.model === "string" && body.model ? body.model : saved.model;
  const connectionId =
    explicitConnectionId ?? (providerId === "custom" ? saved.connectionId : undefined);

  let apiKey = typeof body.apiKey === "string" ? normalizeApiKey(body.apiKey) : "";
  if (!apiKey) {
    // Reuse the stored key so "Test" works after a previous Connect. A named
    // custom connection has its own vault entry.
    const envVar =
      connectionId
        ? customConnectionKeyEnvVar(connectionId)
        : getProvider(providerId)?.envVar ??
          (providerId === "custom" ? "CUSTOM_LLM_API_KEY" : undefined);
    if (envVar) apiKey = (await resolveProviderKey(envVar)) ?? "";
    if (!apiKey) apiKey = saved.apiKey;
  }

  const authStyle =
    body.authStyle === "bearer" ||
    body.authStyle === "x-api-key" ||
    body.authStyle === "api-key" ||
    body.authStyle === "header"
      ? body.authStyle
      : undefined;

  const result = await testConnection({
    providerId,
    baseUrl,
    model,
    apiKey,
    connectionId,
    authStyle,
    apiKeyHeader: typeof body.apiKeyHeader === "string" ? body.apiKeyHeader : undefined,
    apiKeyPrefix: typeof body.apiKeyPrefix === "string" ? body.apiKeyPrefix : undefined,
    verifyChat: body.verifyChat !== false,
  });
  return NextResponse.json(result);
}

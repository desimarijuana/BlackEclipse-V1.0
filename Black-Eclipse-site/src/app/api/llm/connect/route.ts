import { NextResponse } from "next/server";
import { guardMutation, rateLimit } from "@/lib/api-guard";
import { connectProvider } from "@/lib/agent/connection";
import { deleteProviderKey } from "@/lib/provider-keys";
import { getLLMConfig, setLLMConfig } from "@/lib/settings";
import { getProvider } from "@/lib/providers/registry";
import { invalidateSettingsCache } from "@/lib/settings-route-cache";

export const dynamic = "force-dynamic";
export const maxDuration = 45;

/**
 * POST /api/llm/connect — make a provider connection in ONE atomic action:
 * validate → probe with the correct auth → save the key → activate the config.
 * A bad key never replaces a working setup.
 *
 * Body: { providerId, baseUrl?, model?, apiKey? }
 */
export async function POST(request: Request) {
  const blocked = guardMutation(request, "llm-connect");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });

  const limited = rateLimit("llm-connect", { limit: 12, windowMs: 60_000 });
  if (!limited.ok) {
    return NextResponse.json(
      { ok: false, code: "RATE_LIMITED", message: `Too many attempts — retry in ${limited.retryAfterSec}s.`, models: [] },
      { status: 429 },
    );
  }

  const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
  const providerId = typeof body.providerId === "string" ? body.providerId : "";
  if (!providerId || !getProvider(providerId)) {
    return NextResponse.json(
      { ok: false, code: "UNKNOWN_PROVIDER", message: "Choose a provider first.", models: [] },
      { status: 400 },
    );
  }
  if (providerId === "custom" && (typeof body.baseUrl !== "string" || !body.baseUrl.trim())) {
    return NextResponse.json(
      { ok: false, code: "INVALID_INPUT", message: "A base URL is required for a custom connection.", models: [] },
      { status: 400 },
    );
  }

  const authStyle =
    body.authStyle === "bearer" ||
    body.authStyle === "x-api-key" ||
    body.authStyle === "api-key" ||
    body.authStyle === "header"
      ? body.authStyle
      : undefined;

  const result = await connectProvider({
    providerId,
    baseUrl: typeof body.baseUrl === "string" ? body.baseUrl : undefined,
    model: typeof body.model === "string" ? body.model : undefined,
    apiKey: typeof body.apiKey === "string" ? body.apiKey : undefined,
    name: typeof body.name === "string" ? body.name : undefined,
    connectionId: typeof body.connectionId === "string" ? body.connectionId : undefined,
    authStyle,
    apiKeyHeader: typeof body.apiKeyHeader === "string" ? body.apiKeyHeader : undefined,
    apiKeyPrefix: typeof body.apiKeyPrefix === "string" ? body.apiKeyPrefix : undefined,
  });

  if (result.ok) invalidateSettingsCache();
  return NextResponse.json(result);
}

/**
 * DELETE /api/llm/connect?providerId=… — remove a stored key and, when it is
 * the active provider, deactivate chat honestly instead of leaving a config
 * that cannot work.
 */
export async function DELETE(request: Request) {
  const blocked = guardMutation(request, "llm-connect-delete");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });

  const providerId = new URL(request.url).searchParams.get("providerId") ?? "";
  const provider = getProvider(providerId);
  if (!provider) {
    return NextResponse.json({ error: "Unknown provider" }, { status: 400 });
  }

  const envVar = provider.envVar ?? (providerId === "custom" ? "CUSTOM_LLM_API_KEY" : undefined);
  if (envVar) await deleteProviderKey(envVar);

  const saved = await getLLMConfig();
  if (saved.provider === providerId) {
    await setLLMConfig({ provider: "mock", apiKey: "" });
  }
  invalidateSettingsCache();
  return NextResponse.json({ ok: true });
}

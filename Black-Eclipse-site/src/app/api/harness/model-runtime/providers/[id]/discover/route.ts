import { NextResponse } from "next/server";
import { discoverRuntimeModels, HarnessRuntimeUnavailable } from "@/lib/harness";
import { recordDiscoveredModels } from "@/lib/agent/discovered-models";
import { getLLMPreset } from "@/lib/agent/presets";
import { resolveProviderKey } from "@/lib/provider-keys";
import { llmKeyEnvVar } from "@/lib/settings";

export const dynamic = "force-dynamic";

// POST /api/harness/model-runtime/providers/<id>/discover — probe a live provider
// (a local server's installed models, a hosted API's catalog, a router's model
// list) and register what it serves. A failed probe returns ok:false + reason.
//
// KEY RESOLUTION: the browser never holds the API key for a provider (the
// settings form blanks it), so a request that carries no key would 401 for a
// hosted endpoint (OpenAI, Groq, …). When the body has no key we resolve it
// server-side from the environment/vault for that provider's preset env var —
// the same precedence the runtime uses — and fall back to the preset's default
// base URL when none was sent. The key is used only for this one probe and is
// never echoed back. The discovered ids are written to the durable snapshot, so
// the picker shows them after a reload without re-running discovery.
export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params;
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;

    const preset = getLLMPreset(id);
    const baseUrl =
      typeof body.baseUrl === "string" && body.baseUrl ? body.baseUrl : preset?.baseUrl || undefined;
    let apiKey = typeof body.apiKey === "string" && body.apiKey ? body.apiKey : undefined;
    if (!apiKey) {
      // A preset owns its key; any other hosted endpoint (including the
      // `custom` preset) reads the shared CUSTOM_LLM_API_KEY. Without this a
      // hand-typed API was probed keylessly and always 401'd, even though its
      // key was saved.
      const envVar = preset?.envVar ?? llmKeyEnvVar(baseUrl ?? "", id);
      if (envVar) {
        try {
          apiKey = (await resolveProviderKey(envVar)) ?? undefined;
        } catch {
          // Vault unavailable — the probe proceeds keyless (works for local/public).
        }
      }
    }

    const result = await discoverRuntimeModels(id, {
      baseUrl,
      apiKey,
      model: typeof body.model === "string" ? body.model : undefined,
    });
    // Persist the ids so discovery survives a reload / runtime restart. Best
    // effort: a store failure must not fail the live probe.
    if (result.ok) {
      const ids = result.models.map((m) => m.id).filter(Boolean);
      // `served` is the provider's OWN model list, before the registry merge —
      // the models it genuinely installs/serves. The merged list also contains
      // declared placeholders (`llama3.1`) that may not exist, so only `served`
      // is safe to default to.
      const served = result.served.filter(Boolean);
      if (ids.length) {
        try {
          await recordDiscoveredModels(id, ids, served);
        } catch {
          // Snapshot unavailable — the in-memory registry still has them.
        }
      }
    }
    return NextResponse.json({ success: true, ...result });
  } catch (err) {
    const status = err instanceof HarnessRuntimeUnavailable ? 503 : 500;
    console.error("[api/harness/model-runtime/providers/[id]/discover] POST error:", err);
    return NextResponse.json({ error: "Failed to discover models" }, { status });
  }
}

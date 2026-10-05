import { NextResponse } from "next/server";
import { getLLMConfig } from "@/lib/settings";
import { listModelProviders } from "@/lib/harness";
import { LLM_PRESETS } from "@/lib/agent/presets";
import { resolveProviderKey } from "@/lib/provider-keys";

export const dynamic = "force-dynamic";

// GET /api/harness/chat/models — the composer's model selector options.
//
// Returns the ACTIVE provider/model plus every provider the operator can use
// right now, each with the models the runtime catalog declares for it. A
// provider is `available` when it is keyless (a local server) or a key resolves
// from the environment/vault — determined server-side where the vault lives, and
// only ever reported as a boolean (a key is never returned).
//
// The runtime catalog is best-effort: when the Python runtime is unavailable the
// declared presets are still returned (with their default model), so the picker
// never renders empty.
export async function GET() {
  let active: { provider: string; model: string; baseUrl: string } = {
    provider: "auto",
    model: "",
    baseUrl: "",
  };
  try {
    const cfg = await getLLMConfig();
    active = { provider: cfg.provider, model: cfg.model, baseUrl: cfg.baseUrl };
  } catch {
    // Settings unavailable — the picker still works from the preset list.
  }

  let catalog: Array<{ id?: string; models?: string[]; dynamicDiscovery?: boolean }> = [];
  try {
    catalog = (await listModelProviders()) as typeof catalog;
  } catch {
    catalog = [];
  }
  const byId = new Map(catalog.filter((p) => p?.id).map((p) => [p.id as string, p]));

  const providers = await Promise.all(
    LLM_PRESETS.map(async (preset) => {
      const cat = byId.get(preset.id);
      const models = (cat?.models && cat.models.length ? cat.models : [preset.model]).filter(Boolean);
      let available = Boolean(preset.keyless);
      if (!available && preset.envVar) {
        try {
          available = Boolean(await resolveProviderKey(preset.envVar));
        } catch {
          available = false;
        }
      }
      return {
        id: preset.id,
        label: preset.name,
        baseUrl: preset.baseUrl,
        keyless: Boolean(preset.keyless),
        envVar: preset.envVar ?? null,
        dynamicDiscovery: Boolean(cat?.dynamicDiscovery),
        available,
        models,
      };
    }),
  );

  return NextResponse.json({ success: true, active, providers });
}

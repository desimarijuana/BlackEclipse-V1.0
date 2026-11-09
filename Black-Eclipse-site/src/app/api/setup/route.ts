import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { getLLMPreset } from "@/lib/agent/presets";
import { saveProviderKey, listProviderKeyStatus } from "@/lib/provider-keys";
import { getConfig, setLLMConfig, type LLMProviderName } from "@/lib/settings";
import { invalidateSettingsCache } from "@/lib/settings-route-cache";
import { invalidateSourcePreferenceCache } from "@/lib/data-source-preferences";
import { BUNDLES } from "@/lib/setup/bundles";
import { CAPABILITIES } from "@/lib/setup/capabilities";
import { SOURCES, isSourceId, sourceById } from "@/lib/setup/source-catalog";
import { safeSourceDefaults } from "@/lib/setup/defaults";
import { bundleNeedsAcknowledgement } from "@/lib/setup/bundles";
import { computeCapabilityStatus } from "@/lib/setup/capability-status";
import {
  completeOnboarding,
  getAiStatus,
  readOnboardingState,
  readSourcePreferences,
  markMigrated,
  setupSourcePreferences,
} from "@/lib/setup/state";
import { probeInstall } from "@/lib/setup/existing-install";
import type {
  SetupCompleteInput,
  SetupMode,
  SourcePrefs,
} from "@/lib/setup/types";

export const dynamic = "force-dynamic";

/**
 * Resolve the onboarding flag for this request. A truly new install returns
 * `completed:false`; an upgraded install is marked migrated once and never
 * shown the gate.
 */
async function resolveOnboarding(): Promise<{ completed: boolean; mode: SetupMode; isNewInstall: boolean }> {
  const existing = await readOnboardingState();
  if (existing) return { completed: existing.completed, mode: existing.mode, isNewInstall: false };

  const probe = await probeInstall();
  if (!probe.isNew) {
    await markMigrated();
    return { completed: true, mode: "personal", isNewInstall: false };
  }
  return { completed: false, mode: "personal", isNewInstall: true };
}

export async function GET() {
  try {
    const resolved = await resolveOnboarding();
    const savedPrefs = await readSourcePreferences();
    const mode = resolved.mode;
    const sources = savedPrefs
      ? { ...safeSourceDefaults(mode), ...savedPrefs.sources }
      : await setupSourcePreferences(mode);

    const [ai, keyStatuses, lastCheckRaw] = await Promise.all([
      getAiStatus(),
      listProviderKeyStatus(),
      getConfig("setup_check_v1"),
    ]);
    const keyMap = Object.fromEntries(keyStatuses.map((k) => [k.envVar, k.configured]));
    let lastCheck: { at: string; items: unknown[] } | null = null;
    try {
      if (lastCheckRaw) lastCheck = JSON.parse(lastCheckRaw) as { at: string; items: unknown[] };
    } catch {
      lastCheck = null;
    }

    const capabilities = CAPABILITIES.map((cap) => ({
      id: cap.id,
      label: cap.label,
      description: cap.description,
      status: computeCapabilityStatus(cap, sources, (envVar) => Boolean(keyMap[envVar])),
      includedSources: cap.included,
      connectedSources: cap.connected,
      advancedSources: cap.advanced,
    }));

    const sourceRows = SOURCES.map((s) => ({
      id: s.id,
      label: s.label,
      short: s.short,
      category: s.category,
      tier: s.tier,
      powers: s.powers,
      commercial: s.commercial,
      note: s.note,
      termsUrl: s.termsUrl,
      attribution: s.attribution,
      envVar: s.envVar,
      enabled: sources[s.id] === true,
      keyConfigured: s.envVar ? Boolean(keyMap[s.envVar]) : undefined,
      editable: true,
    }));

    const prices = capabilities.find((c) => c.id === "prices");
    const warnings: string[] = [];
    if (mode === "commercial" && prices?.status !== "ready") {
      warnings.push(
        "Commercial mode with no licensed price provider. Charts and quotes will show UNAVAILABLE until you connect one.",
      );
    } else if (prices?.status !== "ready") {
      warnings.push(
        "Live prices are off. Charts and quotes will show UNAVAILABLE until you connect a provider or enable community sources.",
      );
    }
    if (!ai.configured) {
      warnings.push("Chat has no model configured and will be unavailable until you connect one.");
    }

    return NextResponse.json({
      completed: resolved.completed,
      isNewInstall: resolved.isNewInstall,
      mode,
      ai,
      bundles: BUNDLES.map((b) => ({
        ...b,
        needsAcknowledgement: bundleNeedsAcknowledgement(b.id),
      })),
      capabilities,
      sources: sourceRows,
      acceptedRestrictedSources: savedPrefs?.acceptedRestrictedSources ?? [],
      lastCheck,
      warnings,
    });
  } catch (err) {
    console.error("[api/setup] GET error:", err);
    return NextResponse.json({ error: "Failed to load setup state" }, { status: 500 });
  }
}

function asMode(value: unknown): SetupMode {
  return value === "commercial" ? "commercial" : "personal";
}

function cleanSources(raw: unknown): Record<string, boolean> {
  const out: Record<string, boolean> = {};
  if (!raw || typeof raw !== "object") return out;
  for (const [id, value] of Object.entries(raw as Record<string, unknown>)) {
    if (isSourceId(id) && typeof value === "boolean") out[id] = value;
  }
  return out;
}

async function applyAi(choice: SetupCompleteInput["ai"]): Promise<void> {
  if (!choice) return;

  if (choice.kind === "skip") {
    // Clear any old plaintext key so a skipped setup cannot keep using it.
    await setLLMConfig({ provider: "mock", apiKey: "" });
    return;
  }

  if (choice.kind === "local") {
    const preset = getLLMPreset(choice.presetId);
    if (!preset) throw new Error("Unknown local provider preset");
    await setLLMConfig({
      provider: preset.id as LLMProviderName,
      baseUrl: choice.baseUrl?.trim() || preset.baseUrl,
      model: choice.model?.trim() || preset.model,
      apiKey: "",
    });
    return;
  }

  if (choice.kind === "key") {
    const preset = getLLMPreset(choice.presetId);
    if (!preset?.envVar) throw new Error("Unknown provider preset");
    if (!choice.apiKey || choice.apiKey.trim().length < 8) {
      throw new Error("That API key looks too short");
    }
    await saveProviderKey(preset.envVar, choice.apiKey.trim());
    await setLLMConfig({
      provider: preset.id as LLMProviderName,
      baseUrl: preset.baseUrl,
      model: choice.model?.trim() || preset.model,
      // Empty clears any old plaintext key; getLLMConfig resolves the vault.
      apiKey: "",
    });
    return;
  }

  // Custom OpenAI-compatible endpoint.
  let parsed: URL;
  try {
    parsed = new URL(choice.baseUrl);
  } catch {
    throw new Error("Base URL is not a valid URL");
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new Error("Base URL must be http(s)");
  }
  if (!choice.model?.trim()) throw new Error("Model is required for a custom endpoint");
  if (choice.apiKey?.trim()) {
    await saveProviderKey("CUSTOM_LLM_API_KEY", choice.apiKey.trim());
  }
  await setLLMConfig({
    provider: "custom",
    baseUrl: choice.baseUrl.trim().replace(/\/$/, ""),
    model: choice.model.trim(),
    // The key lives in the encrypted vault, never plaintext in llm_config.
    apiKey: "",
    contextWindow: choice.contextWindow ?? null,
  });
}

export async function POST(request: Request) {
  const blocked = guardMutation(request, "setup-complete");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });

  let body: Record<string, unknown>;
  try {
    body = (await request.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  try {
    const mode = asMode(body.mode);
    const sources = cleanSources(body.sources);
    const accepted = Array.isArray(body.acceptedRestrictedSources)
      ? body.acceptedRestrictedSources.filter((v): v is string => typeof v === "string")
      : [];

    // Validate the advanced acknowledgement before persisting: never silently
    // enable a restricted source.
    for (const [id, enabled] of Object.entries(sources)) {
      if (!enabled) continue;
      const def = sourceById(id);
      if (def?.tier === "advanced" && !accepted.includes(id)) {
        return NextResponse.json(
          { error: `${def.label} requires an explicit acknowledgement` },
          { status: 400 },
        );
      }
    }

    const ai = body.ai && typeof body.ai === "object"
      ? (body.ai as SetupCompleteInput["ai"])
      : undefined;

    await applyAi(ai);

    const result = await completeOnboarding({
      mode,
      bundleId: typeof body.bundleId === "string" ? (body.bundleId as SetupCompleteInput["bundleId"]) : undefined,
      sources,
      acceptedRestrictedSources: accepted,
      ai,
    });

    invalidateSettingsCache();
    invalidateSourcePreferenceCache();
    return NextResponse.json({
      ok: true,
      completed: true,
      mode: result.prefs.mode,
      prefs: result.prefs satisfies SourcePrefs,
    });
  } catch (err) {
    console.error("[api/setup] POST error:", err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to save setup" },
      { status: 400 },
    );
  }
}

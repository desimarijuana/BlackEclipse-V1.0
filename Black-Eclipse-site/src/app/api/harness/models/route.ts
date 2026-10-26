import { NextResponse } from "next/server";
import { listModelProviders, listRuntimeModels, HarnessRuntimeUnavailable } from "@/lib/harness";
import { readDiscoveredModels } from "@/lib/agent/discovered-models";
import { sortModelsNewestFirst } from "@/lib/agent/model-recency";

export const dynamic = "force-dynamic";

// GET /api/harness/models — the universal provider catalog owned by the Python
// runtime (first-party LangChain integrations + every OpenAI-compatible
// endpoint). Models discovered at runtime (an Ollama / LM Studio probe) are
// merged in best-effort, so the Settings model picker can show the operator's
// actually-installed models — not just the static declared sample.
export async function GET() {
  try {
    const providers = await listModelProviders();

    // Every place a discovered model can live, merged in order of freshness:
    //   1. the durable SystemConfig snapshot's `served` set — REPLACED by the
    //      last successful probe, so it is the provider's true current list,
    //   2. the snapshot's accumulated ids and the runtime registry (which hold
    //      declared placeholders too — only `dynamic` entries are discoveries).
    const discoveredByProvider = new Map<string, string[]>();
    const servedByProvider = new Map<string, string[]>();
    try {
      const snapshot = await readDiscoveredModels();
      for (const [id, ids] of Object.entries(snapshot.providers ?? {})) {
        discoveredByProvider.set(id, [...ids]);
      }
      for (const [id, ids] of Object.entries(snapshot.served ?? {})) {
        if (ids.length) servedByProvider.set(id, [...ids]);
      }
    } catch {
      // No durable snapshot — the runtime registry below still contributes.
    }
    try {
      const models = await listRuntimeModels();
      for (const m of models) {
        const list = discoveredByProvider.get(m.providerId) ?? [];
        if (m.id && !list.includes(m.id)) list.push(m.id);
        discoveredByProvider.set(m.providerId, list);
      }
    } catch {
      // Ignore — declared models still render.
    }

    const merged = providers.map((p) => {
      const id = typeof p.id === "string" ? p.id : undefined;
      // The freshest probe result wins; the accumulated set is only a fallback.
      const extra = id ? servedByProvider.get(id) ?? discoveredByProvider.get(id) ?? [] : [];
      if (extra.length === 0) {
        return Array.isArray(p.models) ? { ...p, models: sortModelsNewestFirst(p.models as string[]) } : p;
      }
      const declared = Array.isArray(p.models) ? (p.models as string[]) : [];
      return { ...p, models: sortModelsNewestFirst(Array.from(new Set([...extra, ...declared]))) };
    });

    return NextResponse.json({ success: true, providers: merged });
  } catch (err) {
    const status = err instanceof HarnessRuntimeUnavailable ? 503 : 500;
    console.error("[api/harness/models] GET error:", err);
    return NextResponse.json({ error: "Failed to load model catalog" }, { status });
  }
}

import { NextResponse } from "next/server";
import { listModelProviders, listRuntimeModels, HarnessRuntimeUnavailable } from "@/lib/harness";
import { readDiscoveredModels } from "@/lib/agent/discovered-models";

export const dynamic = "force-dynamic";

// GET /api/harness/models — the universal provider catalog owned by the Python
// runtime (first-party LangChain integrations + every OpenAI-compatible
// endpoint). Models discovered at runtime (an Ollama / LM Studio probe) are
// merged in best-effort, so the Settings model picker can show the operator's
// actually-installed models — not just the static declared sample.
export async function GET() {
  try {
    const providers = await listModelProviders();

    // Every place a discovered model can live, merged in order of durability:
    //   1. the durable SystemConfig snapshot (survives a runtime restart),
    //   2. the runtime's in-process registry (freshest, lost on restart).
    const discoveredByProvider = new Map<string, string[]>();
    try {
      const snapshot = await readDiscoveredModels();
      for (const [id, ids] of Object.entries(snapshot.providers)) {
        discoveredByProvider.set(id, [...ids]);
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
      const extra = id ? discoveredByProvider.get(id) ?? [] : [];
      if (extra.length === 0) return p;
      const declared = Array.isArray(p.models) ? (p.models as string[]) : [];
      return { ...p, models: Array.from(new Set([...extra, ...declared])) };
    });

    return NextResponse.json({ success: true, providers: merged });
  } catch (err) {
    const status = err instanceof HarnessRuntimeUnavailable ? 503 : 500;
    console.error("[api/harness/models] GET error:", err);
    return NextResponse.json({ error: "Failed to load model catalog" }, { status });
  }
}

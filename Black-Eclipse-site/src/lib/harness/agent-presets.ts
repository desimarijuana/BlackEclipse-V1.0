// Agent presets — Python is authoritative.
//
// The front door does NOT define agents or system prompts. It fetches them from
// the Python runtime (`GET /agents`) and caches them for the process. This keeps
// exactly one source of truth for agent identity and prompt content.

import { listAgentsFromRuntime } from "./python-client";

export interface AgentPreset {
  id: string;
  name: string;
  systemPrompt: string;
  tools?: string[];
  maxSteps?: number;
  toolTimeoutMs?: number;
  runTimeoutMs?: number;
}

const DEFAULT_AGENT_ID = "eclipse-agent";

interface PresetCache {
  agents: AgentPreset[];
  defaultAgentId: string;
  fetchedAt: number;
}

const CACHE_TTL_MS = 60_000;
const g = globalThis as unknown as { __harnessAgentCache?: PresetCache };

/** Fetch the authoritative agent presets from the runtime, cached briefly. */
export async function loadAgentPresets(): Promise<PresetCache> {
  if (g.__harnessAgentCache && Date.now() - g.__harnessAgentCache.fetchedAt < CACHE_TTL_MS) {
    return g.__harnessAgentCache;
  }
  const { agents, defaultAgentId } = await listAgentsFromRuntime();
  const cache: PresetCache = {
    agents: agents as unknown as AgentPreset[],
    defaultAgentId: defaultAgentId || DEFAULT_AGENT_ID,
    fetchedAt: Date.now(),
  };
  g.__harnessAgentCache = cache;
  return cache;
}

/**
 * Resolve a preset by id (or the runtime default). Throws when an explicit id
 * is unknown so a bad request fails loudly rather than silently falling back.
 */
export async function getAgentPreset(id?: string): Promise<AgentPreset> {
  const { agents, defaultAgentId } = await loadAgentPresets();
  if (!id) {
    const found = agents.find((a) => a.id === defaultAgentId) ?? agents[0];
    if (!found) throw new Error("The runtime exposes no agents");
    return found;
  }
  const preset = agents.find((a) => a.id === id);
  if (!preset) {
    throw new Error(`Unknown agent "${id}". Known: ${agents.map((a) => a.id).join(", ")}`);
  }
  return preset;
}

/** Test seam: clear the cached presets. */
export function __clearAgentPresetCache(): void {
  g.__harnessAgentCache = undefined;
}

export { DEFAULT_AGENT_ID };

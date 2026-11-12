import { describe, it, expect, vi, beforeEach } from "vitest";

// Agent presets are authoritative in the Python runtime. The front door fetches
// and caches them; it must never carry its own prompt copy.

const listAgentsFromRuntime = vi.fn();

vi.mock("./clients/python-client", () => ({
  listAgentsFromRuntime: (...a: unknown[]) => listAgentsFromRuntime(...a),
}));

import { loadAgentPresets, getAgentPreset, __clearAgentPresetCache, DEFAULT_AGENT_ID } from "./agent-presets";

const AGENTS = [
  {
    id: "eclipse-agent",
    name: "Eclipse Agent",
    systemPrompt: "You are Eclipse Agent.",
    tools: ["get_market_snapshot"],
    maxSteps: 8,
  },
];

beforeEach(() => {
  __clearAgentPresetCache();
  listAgentsFromRuntime.mockReset();
  listAgentsFromRuntime.mockResolvedValue({ agents: AGENTS, defaultAgentId: "eclipse-agent" });
});

describe("getAgentPreset", () => {
  it("returns the runtime default when no id is given", async () => {
    const agent = await getAgentPreset();
    expect(agent.id).toBe(DEFAULT_AGENT_ID);
    expect(agent.systemPrompt).toBe("You are Eclipse Agent.");
  });

  it("returns the requested preset by id", async () => {
    const agent = await getAgentPreset("eclipse-agent");
    expect(agent.name).toBe("Eclipse Agent");
  });

  it("throws for an unknown id rather than silently falling back", async () => {
    await expect(getAgentPreset("nope")).rejects.toThrow(/Unknown agent/);
  });

  it("caches presets so repeated lookups do not refetch", async () => {
    await getAgentPreset();
    await getAgentPreset();
    expect(listAgentsFromRuntime).toHaveBeenCalledTimes(1);
  });

  it("exposes the default through loadAgentPresets", async () => {
    const { defaultAgentId } = await loadAgentPresets();
    expect(defaultAgentId).toBe("eclipse-agent");
  });
});

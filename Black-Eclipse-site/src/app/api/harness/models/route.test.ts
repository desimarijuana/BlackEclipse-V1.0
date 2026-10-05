import { describe, it, expect, vi, beforeEach } from "vitest";

// The Settings model picker reads this catalog. It must include models the
// runtime discovered at probe time (an Ollama install), not only the static
// declared sample, and must degrade honestly when the runtime is down.

const listModelProviders = vi.fn();
const listRuntimeModels = vi.fn();
const readDiscoveredModels = vi.fn();

vi.mock("@/lib/harness", async () => {
  const actual = await vi.importActual<typeof import("@/lib/harness")>("@/lib/harness");
  return {
    ...actual,
    listModelProviders: (...a: unknown[]) => listModelProviders(...a),
    listRuntimeModels: (...a: unknown[]) => listRuntimeModels(...a),
  };
});

vi.mock("@/lib/agent/discovered-models", () => ({
  readDiscoveredModels: (...a: unknown[]) => readDiscoveredModels(...a),
}));

import { GET } from "@/app/api/harness/models/route";

beforeEach(() => {
  listModelProviders.mockReset();
  listRuntimeModels.mockReset();
  readDiscoveredModels.mockReset();
  readDiscoveredModels.mockResolvedValue({ providers: {}, updatedAt: new Date(0).toISOString() });
  listModelProviders.mockResolvedValue([
    { id: "ollama", models: ["llama3.1", "llama3.2"] },
    { id: "openai", models: ["gpt-4o-mini"] },
  ]);
  listRuntimeModels.mockResolvedValue([]);
});

describe("GET /api/harness/models", () => {
  it("returns the declared catalog", async () => {
    const res = await GET();
    const body = await res.json();
    const ollama = body.providers.find((p: { id: string }) => p.id === "ollama");
    expect(ollama.models).toContain("llama3.1");
  });

  it("merges runtime-discovered models into the provider", async () => {
    listRuntimeModels.mockResolvedValue([
      { id: "deepseek-v4.1-flash:cloud", providerId: "ollama" },
      { id: "glm-5.3:cloud", providerId: "ollama" },
    ]);
    const res = await GET();
    const body = await res.json();
    const ollama = body.providers.find((p: { id: string }) => p.id === "ollama");
    expect(ollama.models).toContain("deepseek-v4.1-flash:cloud");
    expect(ollama.models).toContain("glm-5.3:cloud");
    expect(ollama.models).toContain("llama3.1");
  });

  it("does not fail when the runtime registry is unavailable", async () => {
    listRuntimeModels.mockRejectedValue(new Error("runtime down"));
    const res = await GET();
    const body = await res.json();
    expect(body.providers.find((p: { id: string }) => p.id === "ollama").models).toContain("llama3.1");
  });

  it("merges the durable discovered snapshot even when the runtime registry is empty", async () => {
    readDiscoveredModels.mockResolvedValue({
      providers: { ollama: ["qwen3:32b", "deepseek-v4.1-flash:cloud"] },
      updatedAt: new Date().toISOString(),
    });
    listRuntimeModels.mockResolvedValue([]);
    const res = await GET();
    const body = await res.json();
    const ollama = body.providers.find((p: { id: string }) => p.id === "ollama");
    expect(ollama.models).toContain("qwen3:32b");
    expect(ollama.models).toContain("deepseek-v4.1-flash:cloud");
    expect(ollama.models).toContain("llama3.1");
  });
});

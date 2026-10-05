import { describe, it, expect, vi, beforeEach } from "vitest";

// The composer's model-options route must report availability from the REAL
// vault/env state and never leak a key — only booleans. This locks the contract
// the composer selector depends on.

const getLLMConfig = vi.fn();
const listModelProviders = vi.fn();
const resolveProviderKey = vi.fn();

vi.mock("@/lib/settings", () => ({ getLLMConfig: (...a: unknown[]) => getLLMConfig(...a) }));
vi.mock("@/lib/harness", () => ({ listModelProviders: (...a: unknown[]) => listModelProviders(...a) }));
vi.mock("@/lib/provider-keys", () => ({ resolveProviderKey: (...a: unknown[]) => resolveProviderKey(...a) }));

import { GET } from "@/app/api/harness/chat/models/route";

beforeEach(() => {
  getLLMConfig.mockReset();
  listModelProviders.mockReset();
  resolveProviderKey.mockReset();
  getLLMConfig.mockResolvedValue({ provider: "deepseek", model: "deepseek-chat", baseUrl: "https://api.deepseek.com/v1" });
  listModelProviders.mockResolvedValue([
    { id: "deepseek", models: ["deepseek-chat", "deepseek-reasoner"], dynamicDiscovery: false },
    { id: "ollama", models: ["llama3.1"], dynamicDiscovery: true },
  ]);
  resolveProviderKey.mockResolvedValue(null);
});

describe("GET /api/harness/chat/models", () => {
  it("returns the active provider/model and the preset list", async () => {
    const res = await GET();
    const body = await res.json();
    expect(body.active.provider).toBe("deepseek");
    expect(body.active.model).toBe("deepseek-chat");
    const deepseek = body.providers.find((p: { id: string }) => p.id === "deepseek");
    expect(deepseek.models).toContain("deepseek-reasoner");
    // Local/keyless providers are always available.
    const ollama = body.providers.find((p: { id: string }) => p.id === "ollama");
    expect(ollama.available).toBe(true);
    expect(ollama.keyless).toBe(true);
  });

  it("reports a hosted provider as available only when a key resolves", async () => {
    resolveProviderKey.mockImplementation(async (envVar: string) => (envVar === "OPENAI_API_KEY" ? "sk-x" : null));
    const res = await GET();
    const body = await res.json();
    const openai = body.providers.find((p: { id: string }) => p.id === "openai");
    const deepseek = body.providers.find((p: { id: string }) => p.id === "deepseek");
    expect(openai.available).toBe(true);
    expect(deepseek.available).toBe(false);
  });

  it("never returns a key-shaped value in any provider entry", async () => {
    resolveProviderKey.mockResolvedValue("secret-value");
    const res = await GET();
    const text = JSON.stringify(await res.json());
    expect(text).not.toContain("secret-value");
    expect(text).not.toContain("apiKey");
  });

  it("still returns the declared presets when the runtime catalog is unavailable", async () => {
    listModelProviders.mockRejectedValue(new Error("runtime down"));
    const res = await GET();
    const body = await res.json();
    expect(body.providers.length).toBeGreaterThan(0);
    const openai = body.providers.find((p: { id: string }) => p.id === "openai");
    expect(openai.models.length).toBeGreaterThan(0);
  });
});

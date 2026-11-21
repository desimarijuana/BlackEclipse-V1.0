import { describe, it, expect, vi, beforeEach } from "vitest";

// Regression tests for the AI / LLM config persistence. The bug these cover:
// a keyless local endpoint stored the sentinel `"local"` as its apiKey; switching
// to a hosted provider kept that sentinel, so the runtime sent "local" as the
// credential (HTTP 401) and the operator could not "add my API key".

const store = new Map<string, string>();
const storedProviderKey = vi.fn(async (_envVar: string): Promise<string | null> => null);

vi.mock("@/lib/db", () => ({
  prisma: {
    systemConfig: {
      findUnique: async ({ where }: { where: { key: string } }) =>
        store.has(where.key) ? { key: where.key, value: store.get(where.key)! } : null,
      upsert: async ({ where, create, update }: { where: { key: string }; create: { value: string }; update: { value: string } }) => {
        store.set(where.key, (update?.value ?? create?.value) as string);
        return { key: where.key, value: store.get(where.key) };
      },
    },
  },
}));
vi.mock("@/lib/provider-keys", () => ({
  storedProviderKey: (envVar: string) => storedProviderKey(envVar),
}));

import {
  getLLMConfig,
  setLLMConfig,
  llmKeyEnvVar,
  LOCAL_KEY_SENTINEL,
  DEFAULT_LLM_CONFIG,
} from "@/lib/settings";

beforeEach(() => {
  store.clear();
  storedProviderKey.mockReset();
  storedProviderKey.mockResolvedValue(null);
  delete process.env.OPENAI_API_KEY;
  delete process.env.ANTHROPIC_API_KEY;
});

describe("setLLMConfig / getLLMConfig", () => {
  it("stores the local sentinel for a keyless local endpoint but never returns it once remote", async () => {
    await setLLMConfig({ provider: "ollama", baseUrl: "http://localhost:11434/v1", model: "llama3.1", apiKey: "" });
    // Persisted form carries the sentinel so the OpenAI-compatible client is happy.
    expect(JSON.parse(store.get("llm_config")!).apiKey).toBe(LOCAL_KEY_SENTINEL);

    // Switch to a remote provider WITHOUT a plaintext key, but with a vault key.
    storedProviderKey.mockResolvedValue("sk-vault-real-key");
    await setLLMConfig({ provider: "openai", baseUrl: "https://api.openai.com/v1", model: "gpt-4o-mini" });

    const effective = await getLLMConfig();
    expect(effective.provider).toBe("openai");
    // The sentinel must NOT shadow the real vault key.
    expect(effective.apiKey).toBe("sk-vault-real-key");
  });

  it("uses the custom-endpoint vault key for a hand-typed base URL", async () => {
    // A base URL the preset list does not own is a custom API. Its key lives in
    // the same vault entry the "Custom provider" preset uses, so saving and the
    // runtime both resolve it instead of failing with "API key is required".
    storedProviderKey.mockImplementation(async (envVar: string) =>
      envVar === "CUSTOM_LLM_API_KEY" ? "sk-acme-real-key" : null,
    );
    await setLLMConfig({
      provider: "custom",
      baseUrl: "https://api.acme.example/v1",
      model: "acme-1",
    });
    const effective = await getLLMConfig();
    // Resolution happens on READ (the persisted row never holds the key), so
    // the custom vault entry is looked up by getLLMConfig.
    expect(storedProviderKey).toHaveBeenCalledWith("CUSTOM_LLM_API_KEY");
    expect(effective.apiKey).toBe("sk-acme-real-key");
    expect(effective.baseUrl).toBe("https://api.acme.example/v1");
  });

  it("resolves a named custom connection's own vault entry", async () => {
    storedProviderKey.mockImplementation(async (envVar: string) =>
      envVar === "CUSTOM_LLM_KEY_MY_GATEWAY" ? "conn-key" : null,
    );
    await setLLMConfig({
      provider: "custom",
      connectionId: "my-gateway",
      baseUrl: "https://gateway.example/v1",
      model: "m1",
    });
    const effective = await getLLMConfig();
    expect(effective.connectionId).toBe("my-gateway");
    expect(effective.apiKey).toBe("conn-key");
    expect(llmKeyEnvVar("https://gateway.example/v1", "custom", "my-gateway")).toBe(
      "CUSTOM_LLM_KEY_MY_GATEWAY",
    );
  });

  it("keeps a named provider's own key when its base URL is edited", async () => {
    // A regional endpoint / company proxy is still the same provider. Reading
    // the base URL first used to resolve to CUSTOM_LLM_API_KEY and strand the
    // key that the connect flow stored under OPENAI_API_KEY.
    storedProviderKey.mockImplementation(async (envVar: string) =>
      envVar === "OPENAI_API_KEY" ? "sk-openai-real" : null,
    );
    await setLLMConfig({
      provider: "openai",
      baseUrl: "https://openai.internal.example/v1",
      model: "gpt-4o-mini",
    });
    const effective = await getLLMConfig();
    expect(effective.apiKey).toBe("sk-openai-real");
  });

  it("persists a remote provider even before a key exists (needs-key, not a save failure)", async () => {
    // Persisting the provider first is what lets the connect UI save the
    // selection and then add the key without the server silently rejecting the
    // edit. Chat still refuses to run until a key resolves.
    storedProviderKey.mockResolvedValue(null);
    const saved = await setLLMConfig({
      provider: "openai",
      baseUrl: "https://api.openai.com/v1",
      model: "gpt-4o-mini",
      apiKey: "",
    });
    expect(saved.provider).toBe("openai");
    const effective = await getLLMConfig();
    expect(effective.apiKey).toBe("");
  });

  it("accepts a remote provider when the vault holds the key", async () => {
    storedProviderKey.mockResolvedValue("sk-vault-real-key");
    const saved = await setLLMConfig({
      provider: "openai",
      baseUrl: "https://api.openai.com/v1",
      model: "gpt-4o-mini",
    });
    expect(saved.provider).toBe("openai");
  });

  it("accepts a remote provider when the environment holds the key", async () => {
    process.env.OPENAI_API_KEY = "sk-env-real-key";
    const saved = await setLLMConfig({
      provider: "openai",
      baseUrl: "https://api.openai.com/v1",
      model: "gpt-4o-mini",
    });
    expect(saved.provider).toBe("openai");
  });

  it("never writes a plaintext key into the persisted row for a remote provider", async () => {
    storedProviderKey.mockResolvedValue("sk-vault-real-key");
    await setLLMConfig({ provider: "openai", baseUrl: "https://api.openai.com/v1", model: "gpt-4o-mini" });
    const persisted = JSON.parse(store.get("llm_config")!);
    expect(persisted.apiKey ?? "").not.toContain("sk-vault-real-key");
  });

  it("keeps the default baseUrl/model when cleared fields are omitted", async () => {
    const cfg = await getLLMConfig();
    expect(cfg.baseUrl).toBe(DEFAULT_LLM_CONFIG.baseUrl);
  });

  it("persists a reasoning-effort override and clears it back to Auto on null", async () => {
    storedProviderKey.mockResolvedValue("sk-vault-real-key");
    await setLLMConfig({
      provider: "openai",
      baseUrl: "https://api.openai.com/v1",
      model: "o3-mini",
      reasoningEffort: "very_high",
    });
    expect((await getLLMConfig()).reasoningEffort).toBe("very_high");

    // An explicit null (the UI's "Auto") must CLEAR it, not keep the old value.
    await setLLMConfig({ reasoningEffort: null });
    expect((await getLLMConfig()).reasoningEffort).toBeUndefined();
  });

  it("persists sampling defaults and clamps them to what providers accept", async () => {
    await setLLMConfig({ provider: "ollama", baseUrl: "http://localhost:11434/v1", model: "llama3.1", apiKey: "" });

    await setLLMConfig({ temperature: 1.4, maxTokens: 512.9 });
    const saved = await getLLMConfig();
    expect(saved.temperature).toBe(1.4);
    expect(saved.maxTokens).toBe(512);

    // Out-of-range values are sanitized, never persisted raw.
    await setLLMConfig({ temperature: 9, maxTokens: 0 });
    const clamped = await getLLMConfig();
    expect(clamped.temperature).toBe(2);
    expect(clamped.maxTokens).toBeUndefined();
  });

  it("clears sampling defaults back to Auto on explicit null", async () => {
    await setLLMConfig({ provider: "ollama", baseUrl: "http://localhost:11434/v1", model: "llama3.1", apiKey: "" });
    await setLLMConfig({ temperature: 0.3, maxTokens: 1024 });

    await setLLMConfig({ temperature: null, maxTokens: null });
    const cfg = await getLLMConfig();
    expect(cfg.temperature).toBeUndefined();
    expect(cfg.maxTokens).toBeUndefined();
  });
});

describe("llmKeyEnvVar", () => {
  it("finds the key for a preset, any custom hosted endpoint, and no key for a local server", () => {
    // Presets own their env var. The two OpenCode plans are separate
    // connections since v0.4.21 (Go → OPENCODE_GO_API_KEY, Zen → OPENCODE_API_KEY);
    // sharing one key made connecting Go mark Zen connected.
    expect(llmKeyEnvVar("https://opencode.ai/inference/openai/v1")).toBe("OPENCODE_API_KEY");
    expect(llmKeyEnvVar("https://opencode.ai/inference/go/openai/v1")).toBe("OPENCODE_GO_API_KEY");
    // Anything else hosted is a custom API: its key is what discovery probes with.
    expect(llmKeyEnvVar("https://opencode.ai/inference/go/v1")).toBe("CUSTOM_LLM_API_KEY");
    expect(llmKeyEnvVar("https://api.acme.example/v1", "custom")).toBe("CUSTOM_LLM_API_KEY");
    // A local server needs none.
    expect(llmKeyEnvVar("http://localhost:11434/v1")).toBeUndefined();
  });
});

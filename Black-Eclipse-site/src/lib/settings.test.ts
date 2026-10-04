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

  it("refuses a remote provider only when neither the vault nor env holds a key", async () => {
    await expect(
      setLLMConfig({ provider: "openai", baseUrl: "https://api.openai.com/v1", model: "gpt-4o-mini", apiKey: "" }),
    ).rejects.toThrow(/API key/i);
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
});

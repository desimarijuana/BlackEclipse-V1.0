import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  PROVIDERS,
  authHeadersFor,
  detectProviderFromKey,
  getProvider,
  normalizeApiKey,
  normalizeBaseUrl,
  providerForBaseUrl,
} from "./registry";

describe("provider registry", () => {
  it("recognises unambiguous key prefixes", () => {
    expect(detectProviderFromKey("sk-ant-api03-abcdef123456")?.id).toBe("anthropic");
    expect(detectProviderFromKey("sk-or-v1-abcdef123456")?.id).toBe("openrouter");
    expect(detectProviderFromKey("gsk_abcdef123456")?.id).toBe("groq");
    expect(detectProviderFromKey("sk-proj-abcdef123456")?.id).toBe("openai");
    expect(detectProviderFromKey("AIzaSyabcdef123456")?.id).toBe("google");
    expect(detectProviderFromKey("xai-abcdef123456")?.id).toBe("xai");
  });

  it("does not guess when a prefix is shared by several providers", () => {
    // A bare `sk-` is used by OpenAI, DeepSeek and others; the user must pick.
    expect(detectProviderFromKey("sk-abcdef123456")).toBeNull();
    expect(detectProviderFromKey("hello")).toBeNull();
  });

  it("cleans a pasted key without damaging it", () => {
    expect(normalizeApiKey('  "Bearer sk-ant-123456"  ')).toBe("sk-ant-123456");
    expect(normalizeApiKey("sk-abc def")).toBe("sk-abcdef");
  });

  it("normalises base URLs people paste", () => {
    expect(normalizeBaseUrl("api.example.com/v1/")).toBe("https://api.example.com/v1");
    expect(normalizeBaseUrl("localhost:11434/v1")).toBe("http://localhost:11434/v1");
    expect(normalizeBaseUrl('"https://api.example.com/v1/"')).toBe("https://api.example.com/v1");
    expect(normalizeBaseUrl("https://api.example.com/v1/chat/completions")).toBe(
      "https://api.example.com/v1",
    );
    expect(normalizeBaseUrl("not a url")).toBeNull();
  });

  it("builds the real auth headers per provider", () => {
    expect(authHeadersFor(getProvider("openai"), "sk-1")).toEqual({
      authorization: "Bearer sk-1",
    });
    expect(authHeadersFor(getProvider("anthropic"), "sk-ant-1")).toMatchObject({
      "x-api-key": "sk-ant-1",
      "anthropic-version": "2023-06-01",
    });
    expect(authHeadersFor(getProvider("google"), "AIza1")).toEqual({
      "x-goog-api-key": "AIza1",
    });
    expect(authHeadersFor(getProvider("ollama"), "")).toEqual({});
  });

  it("matches a saved local URL with or without /v1", () => {
    expect(providerForBaseUrl("http://localhost:11434")?.id).toBe("ollama");
    expect(providerForBaseUrl("http://localhost:11434/v1")?.id).toBe("ollama");
    expect(providerForBaseUrl("https://api.openai.com/v1")?.id).toBe("openai");
  });

  it("stays in step with the Python runtime catalog", () => {
    // Three drifting provider tables caused UI buttons and runtime behaviour to
    // disagree. This guard makes a new UI provider without a runtime row (or a
    // removed runtime row) fail the build instead of in front of a user.
    const here = fileURLToPath(new URL("./registry.ts", import.meta.url));
    const registrySource = readFileSync(here, "utf8");
    const pythonFile = fileURLToPath(
      new URL("../../../python/harness/models.py", import.meta.url),
    );
    const pythonSource = readFileSync(pythonFile, "utf8");
    const pythonIds = new Set(
      [...pythonSource.matchAll(/^\s{4}"([a-z0-9-]+)":\s*ProviderSpec\(/gm)].map((m) => m[1]),
    );
    const uiIds = [...registrySource.matchAll(/^\s{4}id:\s*"([a-z0-9-]+)"/gm)].map((m) => m[1]);
    expect(uiIds.length).toBeGreaterThan(10);
    for (const id of uiIds) {
      expect(pythonIds.has(id), `${id} is missing from python/harness/models.py`).toBe(true);
    }
    expect(PROVIDERS.length).toBe(uiIds.length);
  });

  it("declares OpenCode's required session header and catalog URL", () => {
    const go = getProvider("opencode-go");
    expect(go?.sessionHeader).toBe("x-opencode-session");
    expect(go?.modelsUrl).toBe("https://opencode.ai/inference/go/v1/models");
    expect(getProvider("opencode")?.sessionHeader).toBe("x-opencode-session");
  });

  it("has a vault entry for every keyed provider", () => {
    // A Connect for a provider whose envVar is missing from PROVIDER_KEYS would
    // fail with "Unknown provider key" after a successful probe.
    const vaultFile = fileURLToPath(new URL("../provider-keys.ts", import.meta.url));
    const vaultSource = readFileSync(vaultFile, "utf8");
    for (const provider of PROVIDERS) {
      if (!provider.envVar) continue;
      expect(
        vaultSource.includes(`envVar: '${provider.envVar}'`),
        `${provider.id} envVar ${provider.envVar} is missing from provider-keys.ts`,
      ).toBe(true);
    }
  });
});

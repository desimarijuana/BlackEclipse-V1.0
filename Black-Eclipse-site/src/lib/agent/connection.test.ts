import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/provider-keys", () => ({
  saveProviderKey: vi.fn(async () => undefined),
  storedProviderKey: vi.fn(async () => null),
}));
vi.mock("@/lib/settings", () => ({
  setLLMConfig: vi.fn(async () => ({})),
  llmKeyEnvVar: vi.fn((_baseUrl: string, provider?: string, connectionId?: string) => {
    if (provider === "custom") {
      return connectionId ? `CUSTOM_LLM_KEY_${connectionId.toUpperCase().replace(/-/g, "_")}` : "CUSTOM_LLM_API_KEY";
    }
    if (provider === "openai") return "OPENAI_API_KEY";
    return undefined;
  }),
}));
vi.mock("@/lib/privacy", () => ({
  assertModelAllowed: vi.fn(() => undefined),
}));
vi.mock("./custom-connections", () => ({
  getCustomConnection: vi.fn(async () => null),
  saveCustomConnection: vi.fn(async (input: Record<string, unknown>) => ({
    id: "test-conn",
    name: (input.name as string) || "Custom connection",
    baseUrl: input.baseUrl,
    model: input.model,
    authStyle: input.authStyle || "bearer",
    apiKeyHeader: input.apiKeyHeader,
    apiKeyPrefix: input.apiKeyPrefix,
    createdAt: "2026-11-20T00:00:00.000Z",
    updatedAt: "2026-11-20T00:00:00.000Z",
  })),
  authForConnection: (c: { authStyle: string; apiKeyHeader?: string; apiKeyPrefix?: string }) => {
    if (c.authStyle === "x-api-key") return { header: "x-api-key", prefix: c.apiKeyPrefix || "" };
    if (c.authStyle === "api-key") return { header: "api-key", prefix: c.apiKeyPrefix || "" };
    if (c.authStyle === "header") {
      return { header: c.apiKeyHeader || "authorization", prefix: c.apiKeyPrefix || "" };
    }
    return { header: "authorization", prefix: "Bearer " };
  },
  customConnectionKeyEnvVar: (id: string) => `CUSTOM_LLM_KEY_${id.toUpperCase().replace(/-/g, "_")}`,
}));

import {
  connectProvider,
  effectiveModel,
  parseModelList,
  probeModels,
  testConnection,
} from "./connection";
import { saveProviderKey } from "@/lib/provider-keys";
import { setLLMConfig } from "@/lib/settings";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("parseModelList", () => {
  it("reads the common response shapes and strips Google's models/ prefix", () => {
    expect(parseModelList({ data: [{ id: "a" }, { id: "b" }] })).toEqual(["a", "b"]);
    expect(parseModelList({ models: [{ name: "models/gemini-2.0-flash" }] })).toEqual([
      "gemini-2.0-flash",
    ]);
    expect(parseModelList({ data: { models: [{ id: "x" }] } })).toEqual(["x"]);
    expect(parseModelList(["a", "a", "b"])).toEqual(["a", "b"]);
  });
});

describe("effectiveModel", () => {
  it("never picks an embedding/audio model just because it is first", () => {
    expect(
      effectiveModel({ provider: { model: "retired-model" }, model: "" }, [
        "text-embedding-3-small",
        "whisper-1",
        "llama-3.1-8b",
      ]),
    ).toBe("llama-3.1-8b");
  });

  it("prefers the declared default when the provider still serves it", () => {
    expect(
      effectiveModel({ provider: { model: "gpt-4o-mini" }, model: "" }, [
        "text-embedding-3-small",
        "gpt-4o-mini",
      ]),
    ).toBe("gpt-4o-mini");
  });

  it("always honours an explicit choice", () => {
    expect(
      effectiveModel({ provider: { model: "a" }, model: "explicit" }, ["b", "c"]),
    ).toBe("explicit");
  });
});

describe("probeModels auth", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("sends Anthropic's x-api-key, not a Bearer header", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => jsonResponse({ data: [{ id: "claude-3-5-sonnet-latest" }] }));
    vi.stubGlobal("fetch", fetchMock);
    const result = await probeModels({
      provider: {
        id: "anthropic",
        name: "Anthropic",
        description: "",
        protocol: "anthropic",
        authStyle: "x-api-key",
        baseUrl: "https://api.anthropic.com/v1",
        model: "claude-3-5-sonnet-latest",
        tier: "paid",
      },
      baseUrl: "https://api.anthropic.com/v1",
      apiKey: "sk-ant-test",
      model: "claude-3-5-sonnet-latest",
    });
    expect(result.ok).toBe(true);
    expect(result.models).toEqual(["claude-3-5-sonnet-latest"]);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("https://api.anthropic.com/v1/models");
    expect((init as RequestInit).headers).toMatchObject({
      "x-api-key": "sk-ant-test",
      "anthropic-version": "2023-06-01",
    });
  });

  it("sends Gemini's x-goog-api-key to the native models endpoint", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => jsonResponse({ models: [{ name: "models/gemini-2.0-flash" }] }));
    vi.stubGlobal("fetch", fetchMock);
    const result = await probeModels({
      provider: {
        id: "google",
        name: "Google Gemini",
        description: "",
        protocol: "google",
        authStyle: "x-goog-api-key",
        baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai",
        model: "gemini-2.0-flash",
        tier: "free-tier",
      },
      baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai",
      apiKey: "AIza-test",
      model: "gemini-2.0-flash",
    });
    expect(result.ok).toBe(true);
    expect(result.models).toEqual(["gemini-2.0-flash"]);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("https://generativelanguage.googleapis.com/v1beta/models");
    expect((init as RequestInit).headers).toMatchObject({ "x-goog-api-key": "AIza-test" });
  });

  it("reports a rejected key honestly", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ error: "bad key" }, 401)));
    const result = await probeModels({
      provider: {
        id: "openai",
        name: "OpenAI",
        description: "",
        protocol: "openai",
        authStyle: "bearer",
        baseUrl: "https://api.openai.com/v1",
        model: "gpt-4o-mini",
        tier: "paid",
      },
      baseUrl: "https://api.openai.com/v1",
      apiKey: "sk-bad",
      model: "gpt-4o-mini",
    });
    expect(result.ok).toBe(false);
    expect(result.code).toBe("KEY_REJECTED");
    expect(result.message).toContain("rejected the key");
  });

  it("sends OpenCode's x-opencode-session and a real user agent", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      jsonResponse({ data: [{ id: "kimi-k3" }] }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const result = await probeModels({
      provider: {
        id: "opencode-go",
        name: "OpenCode Go",
        description: "",
        protocol: "openai",
        authStyle: "bearer",
        baseUrl: "https://opencode.ai/inference/go/openai/v1",
        model: "kimi-k3",
        modelsUrl: "https://opencode.ai/inference/go/v1/models",
        sessionHeader: "x-opencode-session",
        tier: "paid",
      },
      baseUrl: "https://opencode.ai/inference/go/openai/v1",
      apiKey: "oc_sk_test",
      model: "kimi-k3",
    });
    expect(result.ok).toBe(true);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("https://opencode.ai/inference/go/v1/models");
    const headers = (init as RequestInit).headers as Record<string, string>;
    expect(headers["x-opencode-session"]).toBeTruthy();
    expect(String(headers["x-opencode-session"]).length).toBeGreaterThan(8);
    expect(headers["user-agent"]).toContain("BlackEclipse");
  });

  it("requires a key for a remote provider without making a request", async () => {
    const fetchMock = vi.fn(async () => {
      throw new Error("probe must not run without a key");
    });
    vi.stubGlobal("fetch", fetchMock);
    const result = await testConnection({ providerId: "openai", apiKey: "" });
    expect(result.ok).toBe(false);
    expect(result.code).toBe("MISSING_KEY");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("connectProvider atomicity", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.mocked(saveProviderKey).mockClear();
    vi.mocked(setLLMConfig).mockClear();
  });

  it("persists the key and config only after a successful probe", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/models")) return jsonResponse({ data: [{ id: "gpt-4o-mini" }] });
        return jsonResponse({ choices: [{ message: { content: "p" } }] });
      }),
    );
    const result = await connectProvider({
      providerId: "openai",
      apiKey: "sk-good",
      model: "gpt-4o-mini",
    });
    expect(result.ok).toBe(true);
    expect(saveProviderKey).toHaveBeenCalledWith("OPENAI_API_KEY", "sk-good");
    expect(setLLMConfig).toHaveBeenCalledWith(
      expect.objectContaining({ provider: "openai", model: "gpt-4o-mini", apiKey: "" }),
    );
  });

  it("stores a key for a custom endpoint (keyless means optional, not discarded)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/models")) return jsonResponse({ data: [{ id: "custom-1" }] });
        return jsonResponse({ choices: [{ message: { content: "p" } }] });
      }),
    );
    const result = await connectProvider({
      providerId: "custom",
      baseUrl: "https://gateway.example/v1",
      apiKey: "custom-key",
      model: "custom-1",
    });
    expect(result.ok).toBe(true);
    // A named connection has its OWN vault entry, not the shared legacy slot.
    expect(saveProviderKey).toHaveBeenCalledWith("CUSTOM_LLM_KEY_TEST_CONN", "custom-key");
    expect(setLLMConfig).toHaveBeenCalledWith(
      expect.objectContaining({ provider: "custom", connectionId: "test-conn" }),
    );
  });

  it("sends a named connection's key in the chosen header", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      jsonResponse({ data: [{ id: "m1" }] }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const result = await testConnection({
      providerId: "custom",
      baseUrl: "https://gateway.example/v1",
      apiKey: "company-key",
      model: "m1",
      authStyle: "x-api-key",
      verifyChat: false,
    });
    expect(result.ok).toBe(true);
    const [, init] = fetchMock.mock.calls[0];
    expect((init as RequestInit).headers).toMatchObject({ "x-api-key": "company-key" });
    expect(((init as RequestInit).headers as Record<string, string>).authorization).toBeUndefined();
  });

  it("supports an api-key header and a custom header with a prefix", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      jsonResponse({ data: [{ id: "m1" }] }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await testConnection({
      providerId: "custom",
      baseUrl: "https://gateway.example/v1",
      apiKey: "azure-key",
      model: "m1",
      authStyle: "api-key",
      verifyChat: false,
    });
    expect((fetchMock.mock.calls[0][1] as RequestInit).headers).toMatchObject({
      "api-key": "azure-key",
    });

    await testConnection({
      providerId: "custom",
      baseUrl: "https://gateway.example/v1",
      apiKey: "abc",
      model: "m1",
      authStyle: "header",
      apiKeyHeader: "x-company-token",
      apiKeyPrefix: "Token ",
      verifyChat: false,
    });
    expect((fetchMock.mock.calls[1][1] as RequestInit).headers).toMatchObject({
      "x-company-token": "Token abc",
    });
  });

  it("does not touch the saved configuration when the probe fails", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ error: "bad key" }, 401)));
    const result = await connectProvider({
      providerId: "openai",
      apiKey: "sk-bad",
      model: "gpt-4o-mini",
    });
    expect(result.ok).toBe(false);
    expect(saveProviderKey).not.toHaveBeenCalled();
    expect(setLLMConfig).not.toHaveBeenCalled();
  });
});


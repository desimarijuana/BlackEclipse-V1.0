import { describe, expect, it, vi } from "vitest";
import { loadModelCatalog, modelsForProvider, type ModelCatalog } from "./model-catalog";

describe("model-catalog helpers", () => {
  const catalog: ModelCatalog = {
    openai: {
      id: "openai",
      contextWindow: 128000,
      models: ["gpt-4o", "gpt-4o-mini"],
      modelWindows: { "gpt-4o": 128000, "gpt-4o-mini": 128000 },
    },
    ollama: { id: "ollama", contextWindow: null, models: ["llama3.1"] },
  };

  it("returns the declared models for a known provider", () => {
    expect(modelsForProvider(catalog, "openai")).toEqual(["gpt-4o", "gpt-4o-mini"]);
  });

  it("returns an empty list for an unknown provider or missing id", () => {
    expect(modelsForProvider(catalog, "does-not-exist")).toEqual([]);
    expect(modelsForProvider(catalog, undefined)).toEqual([]);
  });

  it("preserves an unknown context window as null (never a guess)", () => {
    expect(catalog.ollama.contextWindow).toBeNull();
    expect(catalog.openai.modelWindows?.["gpt-4o"]).toBe(128000);
  });
});

describe("loadModelCatalog", () => {
  it("retries after a failed fetch instead of caching the empty catalog", async () => {
    // The regression: the settings dialog mounts while the Python runtime is
    // still starting, the one fetch 503s, and the empty result was memoised for
    // the whole page — the model picker showed no models until a full reload.
    let fail = true;
    const fetchMock = vi.fn(async () => {
      if (fail) return new Response("{}", { status: 503 });
      return new Response(
        JSON.stringify({ providers: [{ id: "ollama", models: ["kimi-k3:cloud"] }] }),
        { status: 200 },
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    try {
      expect(await loadModelCatalog(true)).toEqual({});
      fail = false;
      const retried = await loadModelCatalog();
      expect(retried.ollama.models).toEqual(["kimi-k3:cloud"]);
      expect(fetchMock).toHaveBeenCalledTimes(2);
    } finally {
      vi.unstubAllGlobals();
    }
  });
});

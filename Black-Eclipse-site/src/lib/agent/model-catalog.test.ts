import { describe, expect, it } from "vitest";
import { modelsForProvider, type ModelCatalog } from "./model-catalog";

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

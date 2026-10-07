import { describe, expect, it } from "vitest";
import {
  SEARCH_PROVIDER_PRESETS,
  searchProviderPreset,
  resolveSearchApiConfig,
} from "@/lib/web-search";

// The operator configures the second search provider by a NAME + key instead of
// hand-writing JSON. These tests pin the resolution rules.

describe("search provider presets", () => {
  it("ships the documented presets", () => {
    const ids = SEARCH_PROVIDER_PRESETS.map((p) => p.id);
    expect(ids).toEqual(["tavily", "brave", "exa", "serper", "searxng"]);
    for (const preset of SEARCH_PROVIDER_PRESETS) {
      expect(preset.config.url).toContain("{query}");
      expect(preset.keyUrl).toMatch(/^https:\/\//);
    }
  });

  it("resolves a preset BY NAME (bare string)", () => {
    const config = resolveSearchApiConfig("tavily");
    expect(config).not.toBeNull();
    expect(config!.url).toContain("tavily.com");
    expect(config!.resultsPath).toBe("results");
  });

  it("resolves a preset given as { preset: name }", () => {
    const config = resolveSearchApiConfig(JSON.stringify({ preset: "brave" }));
    expect(config).not.toBeNull();
    expect(config!.url).toContain("search.brave.com");
    expect(config!.authKind).toBe("header");
  });

  it("lets an explicit field override a preset (self-hosted SearXNG base)", () => {
    const config = resolveSearchApiConfig(JSON.stringify({ preset: "searxng", url: "https://searx.example/search?q={query}&format=json" }));
    expect(config).not.toBeNull();
    expect(config!.url).toBe("https://searx.example/search?q={query}&format=json");
  });

  it("accepts a full hand-written config object unchanged", () => {
    const config = resolveSearchApiConfig(JSON.stringify({
      url: "https://api.example.com/search?q={query}",
      resultsPath: "data.items",
      titlePath: "name",
      urlPath: "link",
      snippetPath: "snippet",
    }));
    expect(config).not.toBeNull();
    expect(config!.resultsPath).toBe("data.items");
    expect(config!.titlePath).toBe("name");
  });

  it("returns null for an unknown preset or an empty/invalid value", () => {
    expect(resolveSearchApiConfig("not-a-real-provider")).toBeNull();
    expect(resolveSearchApiConfig("")).toBeNull();
    expect(resolveSearchApiConfig("{}")).toBeNull();
    expect(resolveSearchApiConfig(null)).toBeNull();
  });

  it("searchProviderPreset finds by id and misses cleanly", () => {
    expect(searchProviderPreset("exa")?.name).toBe("Exa");
    expect(searchProviderPreset("nope")).toBeNull();
  });
});

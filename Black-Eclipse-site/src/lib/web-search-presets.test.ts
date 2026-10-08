import { describe, expect, it } from "vitest";
import {
  SEARCH_PROVIDER_PRESETS,
  searchProviderPreset,
  resolveSearchApiConfig,
  buildPresetSearchProvider,
  firstConfiguredPreset,
} from "@/lib/web-search";

// The operator configures the second search provider by a NAME + key instead of
// hand-writing JSON. These tests pin the resolution rules.

describe("search provider presets", () => {
  it("ships the documented presets", () => {
    const ids = SEARCH_PROVIDER_PRESETS.map((p) => p.id);
    expect(ids).toEqual(["tavily", "brave", "exa", "serper", "serpapi", "bing", "google-cse", "searxng"]);
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

  it("gives every preset its own vault key env", () => {
    for (const p of SEARCH_PROVIDER_PRESETS) {
      expect(p.keyEnv, p.id).toMatch(/^[A-Z0-9_]+$/);
    }
    const envs = SEARCH_PROVIDER_PRESETS.map((p) => p.keyEnv);
    expect(new Set(envs).size).toBe(envs.length);
  });

  it("builds a keyed provider for a named preset (no JSON)", () => {
    const tavily = searchProviderPreset("tavily")!;
    const provider = buildPresetSearchProvider(tavily, "tvly-secret");
    expect(provider).not.toBeNull();
    expect(provider!.withQueryAuth("https://api.tavily.com/search?q=x")).toContain("api_key=tvly-secret");
  });

  it("treats the SearXNG value as a base URL, not a key", () => {
    const searxng = searchProviderPreset("searxng")!;
    const provider = buildPresetSearchProvider(searxng, "https://searx.example");
    expect(provider).not.toBeNull();
    // A keyless provider: the base URL is substituted, no credential appended.
    expect(provider!.withQueryAuth("https://searx.example/search")).not.toContain("key=");
  });

  it("builds nothing when the value is empty", () => {
    expect(buildPresetSearchProvider(searchProviderPreset("brave")!, "")).toBeNull();
    expect(buildPresetSearchProvider(searchProviderPreset("brave")!, null)).toBeNull();
  });

  it("firstConfiguredPreset returns the first key present, in catalogue order", () => {
    const lookup = (envVar: string) => (envVar === "EXA_API_KEY" ? "exa-key" : null);
    const hit = firstConfiguredPreset(lookup);
    expect(hit?.preset.id).toBe("exa");
    expect(hit?.value).toBe("exa-key");
    expect(firstConfiguredPreset(() => null)).toBeNull();
  });
});

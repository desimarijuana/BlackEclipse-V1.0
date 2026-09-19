import { describe, it, expect } from "vitest";
import { buildCatalog, CATEGORY_META } from "./catalog";
import { ECON_SOURCES } from "@/lib/economics/sources";

describe("provider catalog", () => {
  it("groups providers into the declared categories, in order", () => {
    const catalog = buildCatalog({});
    const ids = catalog.categories.map((c) => c.id);
    expect(ids).toEqual(["ai", "economics", "market", "crypto", "custom"]);
    expect(ids.every((id) => id in CATEGORY_META)).toBe(true);
  });

  it("marks built-in providers as always available", () => {
    const catalog = buildCatalog({});
    const flat = catalog.categories.flatMap((c) => c.providers);
    expect(flat.find((p) => p.id === "llm:mock")?.status).toBe("builtin");
    expect(flat.find((p) => p.id === "tradingview")?.status).toBe("builtin");
    expect(flat.find((p) => p.id === "builtin:crypto")?.status).toBe("builtin");
    expect(flat.find((p) => p.id === "kraken")?.status).toBe("builtin");
  });

  it("treats keyless local AI presets as available", () => {
    const catalog = buildCatalog({});
    const flat = catalog.categories.flatMap((c) => c.providers);
    // Ollama and LM Studio need no key, so they are usable out of the box.
    expect(flat.find((p) => p.id === "llm:ollama")?.status).toBe("connected");
    expect(flat.find((p) => p.id === "llm:lmstudio")?.status).toBe("connected");
  });

  it("reports env-gated providers as not_configured when the var is absent", () => {
    const catalog = buildCatalog({});
    const flat = catalog.categories.flatMap((c) => c.providers);
    expect(flat.find((p) => p.id === "llm:openai")?.status).toBe("not_configured");
    expect(flat.find((p) => p.id === "llm:groq")?.status).toBe("not_configured");
    expect(flat.find((p) => p.id === "finnhub")?.status).toBe("not_configured");
    expect(flat.find((p) => p.id === "coingecko")?.status).toBe("not_configured");
  });

  it("reports env-gated providers as connected when the var is set", () => {
    const catalog = buildCatalog({ OPENAI_API_KEY: "sk-test" });
    const flat = catalog.categories.flatMap((c) => c.providers);
    expect(flat.find((p) => p.id === "llm:openai")?.status).toBe("connected");
  });

  it("derives every economics provider from ECON_SOURCES (no drift)", () => {
    const catalog = buildCatalog({});
    const econ = catalog.categories.find((c) => c.id === "economics");
    expect(econ?.providers).toHaveLength(ECON_SOURCES.length);
    const ids = new Set(econ?.providers.map((p) => p.sourceId));
    for (const source of ECON_SOURCES) {
      expect(ids.has(source.id)).toBe(true);
    }
  });

  it("gates key-required economics sources on their env var", () => {
    const withKey = buildCatalog({ FRED_API_KEY: "abc" } );
    const without = buildCatalog({});
    const pick = (catalog: ReturnType<typeof buildCatalog>) =>
      catalog.categories
        .flatMap((c) => c.providers)
        .find((p) => p.sourceId === "fred");
    expect(pick(withKey)?.status).toBe("connected");
    expect(pick(without)?.status).toBe("not_configured");
    expect(pick(without)?.envVar).toBe("FRED_API_KEY");
  });

  it("does not gate keyless economics sources", () => {
    const catalog = buildCatalog({});
    const worldbank = catalog.categories
      .flatMap((c) => c.providers)
      .find((p) => p.sourceId === "worldbank");
    expect(worldbank?.status).toBe("builtin");
    expect(worldbank?.envVar).toBeUndefined();
  });

  it("points every provider somewhere honest to configure", () => {
    const catalog = buildCatalog({});
    const valid = new Set(["ai", "investor-eye", "wizard", "none"]);
    for (const provider of catalog.categories.flatMap((c) => c.providers)) {
      expect(valid.has(provider.configure.target)).toBe(true);
      // A provider that needs configuring must not claim "none".
      if (provider.status === "not_configured") {
        expect(provider.configure.target).not.toBe("none");
      }
    }
  });

  it("counts connected providers per category and in totals", () => {
    const catalog = buildCatalog({});
    const ai = catalog.categories.find((c) => c.id === "ai");
    // Mock + the two keyless local presets (Ollama, LM Studio) work out of the box.
    expect(ai?.connectedCount).toBe(3);
    expect(catalog.totals.providers).toBeGreaterThan(ECON_SOURCES.length);
    expect(catalog.totals.connected).toBeLessThan(catalog.totals.providers);
    expect(catalog.totals.custom).toBeGreaterThan(0);
  });

  it("every provider has a non-empty name and description", () => {
    const catalog = buildCatalog({});
    for (const provider of catalog.categories.flatMap((c) => c.providers)) {
      expect(provider.name.length).toBeGreaterThan(0);
      expect(provider.description.length).toBeGreaterThan(0);
    }
  });
});

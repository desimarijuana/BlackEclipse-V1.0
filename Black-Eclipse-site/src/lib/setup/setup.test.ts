import { describe, expect, it } from "vitest";
import { SOURCES, isSourceId } from "./source-catalog";
import { CAPABILITIES, capabilitySourceIds } from "./capabilities";
import { BUNDLES, bundleSources } from "./bundles";
import { legacySourceDefaults, safeSourceDefaults, isRestrictedSource } from "./defaults";
import { computeCapabilityStatus } from "./capability-status";
import { hasIncludedProbe } from "./included-probes";

describe("setup catalog", () => {
  it("has unique ids and a valid tier/badge for every source", () => {
    const ids = SOURCES.map((s) => s.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const source of SOURCES) {
      expect(isSourceId(source.id)).toBe(true);
      expect(["included", "connected", "advanced"]).toContain(source.tier);
      expect(["ok", "attribution", "personal-only", "verify"]).toContain(source.commercial);
    }
  });

  it("never defaults a connected or advanced source on", () => {
    for (const source of SOURCES) {
      if (source.tier !== "included") expect(source.defaultOn).toBe(false);
    }
  });

  it("declares a reachability probe for every included source", () => {
    for (const source of SOURCES) {
      if (source.tier === "included") {
        expect(hasIncludedProbe(source.id), `${source.id} has no probe`).toBe(true);
      }
    }
  });

  it("shows every source in at least one capability", () => {
    const mapped = new Set(capabilitySourceIds());
    for (const source of SOURCES) expect(mapped.has(source.id)).toBe(true);
    // A source may legitimately power more than one capability (Finnhub is
    // quotes, fundamentals and news), so duplicates are expected.
    expect(mapped.size).toBe(SOURCES.length);
  });
});

describe("setup defaults", () => {
  it("safe defaults enable open data only", () => {
    const safe = safeSourceDefaults("personal");
    for (const source of SOURCES) {
      expect(safe[source.id]).toBe(source.tier === "included" && source.defaultOn);
    }
  });

  it("commercial safe defaults also never enable a restricted source", () => {
    const safe = safeSourceDefaults("commercial");
    for (const source of SOURCES) {
      if (source.tier !== "included") expect(safe[source.id]).toBe(false);
    }
  });

  it("legacy defaults preserve the pre-setup fetch chain", () => {
    const legacy = legacySourceDefaults();
    expect(legacy.tradingview).toBe(true);
    expect(legacy.yfinance).toBe(true);
    expect(legacy.binance).toBe(true);
    expect(legacy.sec).toBe(true);
  });

  it("restricted includes advanced and personal-only sources", () => {
    expect(isRestrictedSource("tradingview")).toBe(true);
    expect(isRestrictedSource("binance")).toBe(true);
    expect(isRestrictedSource("sec")).toBe(false);
  });
});

describe("setup bundles", () => {
  it("ships the five advertised bundles", () => {
    expect(BUNDLES.map((b) => b.id).sort()).toEqual(
      ["commercial", "crypto", "custom", "personal-trader", "research"].sort(),
    );
  });

  it("no bundle enables an advanced or connected source by itself", () => {
    for (const bundle of BUNDLES) {
      for (const mode of ["personal", "commercial"] as const) {
        const sources = bundleSources(bundle.id, mode);
        for (const source of SOURCES) {
          if (source.tier !== "included") expect(sources[source.id]).toBe(false);
        }
      }
    }
  });
});

describe("capability status", () => {
  it("reports included data as ready", () => {
    const cap = CAPABILITIES.find((c) => c.id === "company")!;
    expect(computeCapabilityStatus(cap, safeSourceDefaults("personal"), () => false)).toBe("ready");
    expect(computeCapabilityStatus(cap, { ...safeSourceDefaults("personal"), sec: false }, () => false)).toBe("needs-key");
  });

  it("reports a configured connected provider as ready", () => {
    const cap = CAPABILITIES.find((c) => c.id === "prices")!;
    expect(computeCapabilityStatus(cap, safeSourceDefaults("personal"), () => false)).toBe("needs-key");
    expect(
      computeCapabilityStatus(cap, safeSourceDefaults("personal"), (envVar) => envVar === "POLYGON_API_KEY"),
    ).toBe("ready");
  });

  it("reports an enabled advanced source as ready", () => {
    const cap = CAPABILITIES.find((c) => c.id === "prices")!;
    expect(
      computeCapabilityStatus(
        cap,
        { ...safeSourceDefaults("personal"), tradingview: true },
        () => false,
      ),
    ).toBe("ready");
  });
});

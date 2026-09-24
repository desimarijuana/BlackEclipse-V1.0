import { describe, it, expect } from "vitest";
import { buildCapabilityMatrix } from "./capability";
import { capabilityHealthTargets, healthTargets } from "./coverage";

// WS3: capability-specific, route-specific health. These are pure and offline.

describe("capability-specific health targets", () => {
  it("declares a distinct target per (source × market × assetClass × capability)", () => {
    const targets = capabilityHealthTargets();
    const keys = targets.map((t) => `${t.source}|${t.market}|${t.assetClass}|${t.capability}`);
    expect(new Set(keys).size).toBe(keys.length);
    // The same source+market+assetClass yields SEPARATE quote and statement rows.
    const usQuote = keys.find((k) => k === "LIVE_STRUCTURED|US|equity|live_quote");
    const usStmt = keys.find((k) => k === "JDDS|US|equity|financial_statements");
    expect(usQuote).toBeTruthy();
    expect(usStmt).toBeTruthy();
    expect(usQuote).not.toBe(usStmt);
  });

  it("keeps the legacy quote axis for backwards compatibility", () => {
    expect(healthTargets().length).toBeGreaterThan(0);
  });

  it("includes the credential-gated SEC route as its own target", () => {
    const keys = capabilityHealthTargets().map((t) => `${t.source}|${t.capability}`);
    expect(keys).toContain("SEC|sec_filings");
  });
});

describe("capability matrix observed-health is per-axis", () => {
  it("a working quote does NOT make the statement axis observed-working", () => {
    const matrix = buildCapabilityMatrix({
      universeCounts: { PK: 1312 },
      observedByCapability: { "PK|quote": "working" },
      fundamentalsAvailability: { usFilings: false, keylessVendor: false, multiMarketVendor: false },
      webAvailable: true,
    });
    const pk = matrix.find((m) => m.market === "PK")!;
    expect(pk.quote.observed).toBe("working");
    // No statement health recorded → unknown, never inherited from the quote.
    expect(pk.fundamentals.observed).toBe("unknown");
    expect(pk.filings.observed).toBe("unknown");
  });

  it("reports a failing statement route independently of a healthy quote", () => {
    const matrix = buildCapabilityMatrix({
      observedByCapability: { "TW|quote": "working", "TW|fundamentals": "failing" },
      fundamentalsAvailability: { usFilings: true, keylessVendor: true, multiMarketVendor: false },
    });
    const tw = matrix.find((m) => m.market === "TW")!;
    expect(tw.quote.observed).toBe("working");
    expect(tw.fundamentals.observed).toBe("failing");
  });

  it("zero attempts stays unknown for every axis", () => {
    const matrix = buildCapabilityMatrix({ observedByCapability: {} });
    const jp = matrix.find((m) => m.market === "JP")!;
    expect(jp.quote.observed).toBe("unknown");
    expect(jp.fundamentals.observed).toBe("unknown");
  });

  it("exposes country-aware filing routes rather than a US-only assumption", () => {
    const matrix = buildCapabilityMatrix({
      fundamentalsAvailability: { usFilings: true, keylessVendor: false, multiMarketVendor: false },
    });
    const us = matrix.find((m) => m.market === "US")!;
    const kr = matrix.find((m) => m.market === "KR")!;
    const pk = matrix.find((m) => m.market === "PK")!;
    // US has a direct structured filing route…
    expect(us.filings.level).toBe("configured");
    // …KR/PK name their own regulator route as unconfigured, not "not implemented".
    expect(kr.filings.level).toBe("unconfigured");
    expect(kr.filings.via).toMatch(/DART/);
    expect(pk.filings.level).toBe("unconfigured");
    expect(pk.filings.via).toMatch(/PSX/);
  });
});

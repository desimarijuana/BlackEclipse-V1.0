import { describe, it, expect } from "vitest";
import { splitExchangeSuffix, EXCHANGE_SUFFIX_ALIASES, resolveMarketId, currencyIsoFor } from "./markets";
import { buildCapabilityMatrix, capabilityLine } from "./harness/capability";
import { extractPdfText } from "./web-research";

describe("global exchange-suffix identity", () => {
  it("splits well-known suffixes into a market", () => {
    expect(splitExchangeSuffix("2330.TW")).toEqual({ symbol: "2330", market: "TW" });
    expect(splitExchangeSuffix("005930.KS")).toEqual({ symbol: "005930", market: "KR" });
    expect(splitExchangeSuffix("PETR4.SA")).toEqual({ symbol: "PETR4", market: "BR" });
    expect(splitExchangeSuffix("BHP.AX")).toEqual({ symbol: "BHP", market: "AU" });
    expect(splitExchangeSuffix("SHEL.L")).toEqual({ symbol: "SHEL", market: "UK" });
    expect(splitExchangeSuffix("7203.T")).toEqual({ symbol: "7203", market: "JP" });
    expect(splitExchangeSuffix("RELIANCE.NS")).toEqual({ symbol: "RELIANCE", market: "IN" });
    expect(splitExchangeSuffix("0700.HK")).toEqual({ symbol: "0700", market: "HK" });
  });

  it("does NOT guess an unknown suffix", () => {
    // A dot that is not a recognised exchange suffix is left intact (no guess).
    expect(splitExchangeSuffix("BRK.B")).toEqual({ symbol: "BRK.B", market: null });
    expect(splitExchangeSuffix("ABC.XY")).toEqual({ symbol: "ABC.XY", market: null });
    expect(splitExchangeSuffix("PLAIN")).toEqual({ symbol: "PLAIN", market: null });
  });

  it("resolves each suffix alias to a currency", () => {
    for (const [suffix, market] of Object.entries(EXCHANGE_SUFFIX_ALIASES)) {
      expect(resolveMarketId(suffix), suffix).toBe(market);
    }
    expect(currencyIsoFor("TW")).toBe("TWD");
    expect(currencyIsoFor("KR")).toBe("KRW");
    expect(currencyIsoFor("BR")).toBe("BRL");
    expect(currencyIsoFor("UK")).toBe("GBP");
  });
});

describe("global capability matrix", () => {
  it("does not advertise statements from working quotes", () => {
    const matrix = buildCapabilityMatrix({
      universeCounts: { TW: 2350, US: 11288 },
      observedByMarket: { TW: "working" },
      // No fundamentals route is usable here at all.
      fundamentalsAvailability: { usFilings: false, keylessVendor: false, multiMarketVendor: false },
      webAvailable: true,
    });
    const tw = matrix.find((m) => m.market === "TW")!;
    // TW: quotes work, but with NO provider available statements are NOT configured.
    expect(tw.quote.level).toBe("configured");
    expect(tw.fundamentals.level).not.toBe("configured");
    expect(tw.fundamentals.level).toBe("unconfigured");
    expect(tw.universe).toBe(2350);
  });

  it("marks non-US fundamentals configured when the keyless vendor is usable", () => {
    const matrix = buildCapabilityMatrix({
      fundamentalsAvailability: { usFilings: true, keylessVendor: true, multiMarketVendor: false },
    });
    const kr = matrix.find((m) => m.market === "KR")!;
    // yfinance (keyless, multi-market) genuinely covers Korean issuers.
    expect(kr.fundamentals.level).toBe("configured");
    // But a market with no statement data type at all stays unimplemented.
    const fx = matrix.find((m) => m.market === "FX")!;
    expect(fx.fundamentals.level).toBe("not_implemented");
  });

  it("reports zero-attempt health as unknown, never healthy/failing", () => {
    const matrix = buildCapabilityMatrix({
      universeCounts: { JP: 3897 },
      observedByMarket: {},
      fundamentalsAvailability: { usFilings: true, keylessVendor: false, multiMarketVendor: false },
    });
    const jp = matrix.find((m) => m.market === "JP")!;
    expect(jp.quote.observed).toBe("unknown");
  });

  it("marks a keyed-vendor market as configured only when a vendor is present", () => {
    const withoutVendor = buildCapabilityMatrix({
      fundamentalsAvailability: { usFilings: true, keylessVendor: false, multiMarketVendor: false },
    }).find((m) => m.market === "KR")!;
    expect(withoutVendor.fundamentals.level).toBe("unconfigured");

    const withKeyed = buildCapabilityMatrix({
      fundamentalsAvailability: { usFilings: true, keylessVendor: false, multiMarketVendor: true },
    }).find((m) => m.market === "KR")!;
    expect(withKeyed.fundamentals.level).toBe("configured");
  });

  it("keeps recognised-but-uncovered markets visible", () => {
    const matrix = buildCapabilityMatrix({});
    const deriv = matrix.find((m) => m.market === "DERIV");
    expect(deriv).toBeTruthy();
    expect(deriv!.quote.level).toBe("recognized_only");
  });

  it("produces a compact, non-duplicating line", () => {
    const matrix = buildCapabilityMatrix({ universeCounts: { US: 10 } });
    const line = capabilityLine(matrix.find((m) => m.market === "US")!);
    expect(line).toContain("US");
    expect(line).toContain("fundamentals:");
  });
});

describe("PDF text extraction (bounded, no OCR)", () => {
  it("extracts text-showing operators from an uncompressed PDF", () => {
    const pdf = "%PDF-1.4\n1 0 obj\n<<>>\nstream\n(Consolidated revenue 60,922 million) Tj\nendstream\nendobj\n%%EOF";
    const result = extractPdfText(pdf);
    expect(result.ok).toBe(true);
    expect(result.text).toContain("Consolidated revenue 60,922 million");
  });

  it("reports a scanned/image PDF as having no text layer", () => {
    const pdf = "%PDF-1.4\n1 0 obj\n<< /Subtype /Image >>\nstream\nBINARYDATA\nendstream\nendobj\n%%EOF";
    const result = extractPdfText(pdf);
    expect(result.ok).toBe(false);
    expect(result.note).toMatch(/no extractable text|scanned|OCR/i);
  });
});

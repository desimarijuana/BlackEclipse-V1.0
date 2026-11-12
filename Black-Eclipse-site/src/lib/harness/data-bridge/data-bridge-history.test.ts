import { describe, it, expect } from "vitest";

// The history request's BAR SIZE and WINDOW are different fields.
//
// REGRESSION: `period` was read as the interval, so a request for
// `period: "1y"` asked the provider for a "1y bar" - not a bar size at all.
// The request came back empty, and a multi-year history read as "no data" (or,
// when it did answer, as a handful of monthly bars). The market-tool output
// compounded it by rendering the OLDEST bars, so an analysis reasoned about
// 2021 while the data ran to today.

import { resolveHistoryParams, isMarketDataSymbol, marketDataAssetClass } from "./data-bridge-history";

describe("resolveHistoryParams", () => {
  it("reads a bar size from `interval`", () => {
    expect(resolveHistoryParams({ interval: "1d" }).interval).toBe("1d");
    expect(resolveHistoryParams({ interval: "1wk" }).interval).toBe("1wk");
  });

  it("reads a window from `period` and never as a bar size", () => {
    const params = resolveHistoryParams({ period: "1y" });
    expect(params.interval).toBe("1d");
    expect(params.window).toBe("1y");
  });

  it("reads a window from `range`", () => {
    const params = resolveHistoryParams({ interval: "1d", range: "5y" });
    expect(params.interval).toBe("1d");
    expect(params.window).toBe("5y");
  });

  it("treats an ambiguous value as a WINDOW, not a bar size", () => {
    // "1mo" is both a monthly bar and a one-month window: the window wins.
    const params = resolveHistoryParams({ period: "1mo" });
    expect(params.interval).toBe("1d");
    expect(params.window).toBe("1mo");
  });

  it("honours a bar-size-only value in `period`", () => {
    expect(resolveHistoryParams({ period: "1h" }).interval).toBe("1h");
    expect(resolveHistoryParams({ period: "5m" }).interval).toBe("5m");
  });

  it("defaults to daily bars over a year", () => {
    const params = resolveHistoryParams({});
    expect(params.interval).toBe("1d");
    expect(params.window).toBe("1y");
  });

  it("carries an explicit window through", () => {
    const params = resolveHistoryParams({ start: "2020-01-01", end: "2020-12-31" });
    expect(params.start).toBe("2020-01-01");
    expect(params.end).toBe("2020-12-31");
  });
});

describe("isMarketDataSymbol", () => {
  it("recognises the symbols the equity universe does not hold", () => {
    expect(isMarketDataSymbol("^VIX")).toBe(true);
    expect(isMarketDataSymbol("GC=F")).toBe(true);
    expect(isMarketDataSymbol("DX-Y.NYB")).toBe(true);
    expect(isMarketDataSymbol("^TNX")).toBe(true);
  });

  it("does not claim an ordinary ticker", () => {
    expect(isMarketDataSymbol("GLD")).toBe(false);
    expect(isMarketDataSymbol("AAPL")).toBe(false);
    expect(isMarketDataSymbol("")).toBe(false);
  });

  it("classes them", () => {
    expect(marketDataAssetClass("^VIX")).toBe("index");
    expect(marketDataAssetClass("GC=F")).toBe("commodity");
    expect(marketDataAssetClass("DX-Y.NYB")).toBe("fx");
  });
});

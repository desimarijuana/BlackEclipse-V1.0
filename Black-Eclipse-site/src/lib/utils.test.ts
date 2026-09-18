import { describe, it, expect } from "vitest";
import { getTradingViewSymbol, stripExchangeSuffix } from "./utils";

describe("stripExchangeSuffix", () => {
  it("strips the common Yahoo suffixes", () => {
    expect(stripExchangeSuffix("RELIANCE.NS")).toBe("RELIANCE");
    expect(stripExchangeSuffix("OGDC.PSX")).toBe("OGDC");
    expect(stripExchangeSuffix("SYS.KA")).toBe("SYS");
    expect(stripExchangeSuffix("0001.HK")).toBe("0001");
    expect(stripExchangeSuffix("7203.T")).toBe("7203");
    expect(stripExchangeSuffix("CSPX.L")).toBe("CSPX");
  });

  it("is case-insensitive and normalizes to uppercase", () => {
    expect(stripExchangeSuffix("aapl.us")).toBe("AAPL");
  });

  it("prefers the longest suffix (SW must not be read as W)", () => {
    expect(stripExchangeSuffix("NESN.SW")).toBe("NESN");
    expect(stripExchangeSuffix("ASML.AS")).toBe("ASML");
  });

  it("leaves bare symbols alone", () => {
    expect(stripExchangeSuffix("AAPL")).toBe("AAPL");
    // A symbol that merely ends in letters must not be truncated.
    expect(stripExchangeSuffix("ATCO")).toBe("ATCO");
  });
});

describe("getTradingViewSymbol", () => {
  it("resolves US tickers unchanged", () => {
    expect(getTradingViewSymbol("AAPL")).toBe("AAPL");
  });

  it("maps crypto both ways", () => {
    expect(getTradingViewSymbol("BTC")).toBe("BINANCE:BTCUSDT");
    expect(getTradingViewSymbol("btc-usd", true)).toBe("BINANCE:BTCUSDT");
    expect(getTradingViewSymbol("ETH-USD", true)).toBe("BINANCE:ETHUSDT");
    expect(getTradingViewSymbol("SOLUSDT", true)).toBe("BINANCE:SOLUSDT");
    // The old order stripped bare "USD" before "-USD", producing "BTC-USDT".
    expect(getTradingViewSymbol("BTC-USD", true)).not.toContain("-");
  });

  it("resolves suffixed tickers without a market hint", () => {
    // These previously fell through as raw, unresolvable strings.
    expect(getTradingViewSymbol("0001.HK")).toBe("HKEX:0001");
    expect(getTradingViewSymbol("7203.T")).toBe("TSE:7203");
    expect(getTradingViewSymbol("CSPX.L")).toBe("LSE:CSPX");
    expect(getTradingViewSymbol("RELIANCE.NS")).toBe("NSE:RELIANCE");
    expect(getTradingViewSymbol("OGDC.KA")).toBe("PSX:OGDC");
  });

  it("market-qualifies numeric Asian tickers", () => {
    expect(getTradingViewSymbol("1", false, "HK")).toBe("HKEX:1");
    expect(getTradingViewSymbol("1301", false, "JP")).toBe("TSE:1301");
    expect(getTradingViewSymbol("786", false, "PK")).toBe("PSX:786");
  });

  it("refines Chinese exchanges by code prefix", () => {
    expect(getTradingViewSymbol("600519", false, "CN")).toBe("SSE:600519");
    expect(getTradingViewSymbol("000001", false, "CN")).toBe("SZSE:000001");
    expect(getTradingViewSymbol("300750", false, "CN")).toBe("SZSE:300750");
    expect(getTradingViewSymbol("830799", false, "CN")).toBe("BSE:830799");
  });

  it("strips a suffix before market-qualifying", () => {
    expect(getTradingViewSymbol("0700.HK", false, "HK")).toBe("HKEX:0700");
    expect(getTradingViewSymbol("RELIANCE.NS", false, "IN")).toBe("NSE:RELIANCE");
  });

  it("keeps index and commodity mappings intact", () => {
    expect(getTradingViewSymbol("^GSPC")).toBe("SP:SPX");
    expect(getTradingViewSymbol("KSE100")).toBe("PSX:KSE100");
    expect(getTradingViewSymbol("GC=F")).toBe("TVC:GOLD");
    expect(getTradingViewSymbol("EUR=X")).toBe("FX_IDC:EURUSD");
  });

  it("falls back safely on empty input", () => {
    expect(getTradingViewSymbol("")).toBe("NASDAQ:AAPL");
  });
});

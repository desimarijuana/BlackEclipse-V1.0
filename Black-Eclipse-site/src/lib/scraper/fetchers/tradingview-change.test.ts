import { describe, it, expect } from "vitest";
import { changePctFromAbsolute, yahooSymbol } from "./tradingview";

describe("changePctFromAbsolute", () => {
  it("converts an absolute gain into a positive percentage", () => {
    // 100 -> 110 (change +10) = +10%
    expect(changePctFromAbsolute(110, 10)).toBeCloseTo(10);
  });

  it("converts an absolute loss into a negative percentage", () => {
    // 50 -> 40 (change -10) = -20%
    expect(changePctFromAbsolute(40, -10)).toBeCloseTo(-20);
  });

  it("handles fractional prices", () => {
    // 11.50 -> 11.63 (change 0.13) ≈ +1.13%
    expect(changePctFromAbsolute(11.63, 0.13)).toBeCloseTo(1.1304, 3);
  });

  it("returns 0 for zero/invalid inputs instead of NaN or Infinity", () => {
    expect(changePctFromAbsolute(0, 5)).toBe(0);
    expect(changePctFromAbsolute(10, 0)).toBe(0);
    expect(changePctFromAbsolute(Number.NaN, 1)).toBe(0);
    expect(changePctFromAbsolute(10, Number.NaN)).toBe(0);
  });

  it("never flips sign when a price crosses zero", () => {
    // close 0.02, change +0.03 → prevClose would be negative; must stay positive
    expect(changePctFromAbsolute(0.02, 0.03)).toBeGreaterThan(0);
  });
});

describe("yahooSymbol", () => {
  it("appends the market suffix", () => {
    expect(yahooSymbol("AAPL", "US")).toBe("AAPL");
    expect(yahooSymbol("OGDC", "PK")).toBe("OGDC.PSX");
    expect(yahooSymbol("700", "HK")).toBe("700.HK");
  });

  it("does not double-append an existing suffix", () => {
    expect(yahooSymbol("OGDC.PSX", "PK")).toBe("OGDC.PSX");
  });
});

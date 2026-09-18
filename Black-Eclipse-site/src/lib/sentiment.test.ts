import { describe, it, expect } from "vitest";
import { guessSentiment } from "./sentiment";

describe("guessSentiment", () => {
  it("detects bullish headlines", () => {
    expect(guessSentiment("Stocks rally as earnings beat expectations")).toBe("bullish");
  });

  it("detects bearish headlines", () => {
    expect(guessSentiment("Shares plunge after profit warning and downgrade")).toBe("bearish");
  });

  it("returns neutral when no keywords match", () => {
    expect(guessSentiment("Company announces quarterly board meeting date")).toBe("neutral");
  });

  it("does not match substrings inside other words", () => {
    // "up" inside "startup" / "sup" must NOT count as bullish.
    expect(guessSentiment("Startup founder wins award at ceremony")).toBe("neutral");
    // "down" inside "countdown" must not count as bearish.
    expect(guessSentiment("Countdown begins for rocket launch")).toBe("neutral");
  });

  it("weighs mixed sentiment by keyword count", () => {
    // one bull word vs two bear words → bearish
    expect(guessSentiment("Rally fades as losses mount on lawsuit fears")).toBe("bearish");
  });

  // ── Phrase disambiguation ────────────────────────────────────────────────
  // The core failure class this fixes: a context word like "record" used to be
  // scored bullish on its own, so "record loss" classified bullish.

  it("reads 'record' only in context", () => {
    expect(guessSentiment("Company posts record loss for the quarter")).toBe("bearish");
    expect(guessSentiment("Shares hit record high on strong demand")).toBe("bullish");
  });

  it("scores guidance and estimate phrases", () => {
    expect(guessSentiment("Firm cuts guidance for the full year")).toBe("bearish");
    expect(guessSentiment("Firm raises guidance for the full year")).toBe("bullish");
    expect(guessSentiment("Results beat estimates across the board")).toBe("bullish");
    expect(guessSentiment("Results miss estimates across the board")).toBe("bearish");
  });

  it("normalizes hyphenated phrases", () => {
    // "sell-off" must reach the "sell off" phrase, not two neutral tokens.
    expect(guessSentiment("Broad sell-off grips technology shares")).toBe("bearish");
    // "record-breaking" decomposes so the lexicon word "climb" is still seen;
    // a hyphen glued into one unknown token would hide it.
    expect(guessSentiment("Index climbs to record-breaking level")).toBe("bullish");
  });

  // ── Negation ─────────────────────────────────────────────────────────────
  // "despite"/"although" are concessive, not negating. They used to flip the
  // polarity of whatever followed, inverting correct headlines.

  it("does not treat concessive connectors as negators", () => {
    expect(guessSentiment("Shares rise despite weak guidance")).toBe("neutral");
  });

  it("still negates with real negators", () => {
    expect(guessSentiment("Company fails to beat expectations")).toBe("bearish");
    expect(guessSentiment("Profit did not grow this quarter")).toBe("neutral");
  });
});

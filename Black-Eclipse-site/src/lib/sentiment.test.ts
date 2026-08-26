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
});

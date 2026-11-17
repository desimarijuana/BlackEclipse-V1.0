import { describe, expect, it } from "vitest";
import { backtestLabel } from "./strategy-library";

describe("strategy evidence badges", () => {
  it("says a strategy has no backtest instead of a green badge", () => {
    expect(backtestLabel({ latestBacktest: null })).toEqual({
      text: "no backtest",
      tone: "text-amber-300/80",
    });
  });

  it("marks a completed backtest green", () => {
    expect(backtestLabel({ latestBacktest: { status: "completed" } })).toEqual({
      text: "backtest ✓",
      tone: "text-emerald-300/90",
    });
  });

  it("treats the engine's OK status as a completed backtest", () => {
    expect(backtestLabel({ latestBacktest: { status: "OK" } })).toEqual({
      text: "backtest ✓",
      tone: "text-emerald-300/90",
    });
  });

  it("shows a non-completed status verbatim", () => {
    expect(backtestLabel({ latestBacktest: { status: "failed" } }).text).toBe(
      "backtest failed",
    );
  });
});

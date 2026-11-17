import { describe, expect, it } from "vitest";
import { consumeStrategyTarget, navigateTo, navigateToStrategy } from "./app-nav";

describe("navigation intents", () => {
  it("keeps a strategy target for the studio to consume", () => {
    navigateToStrategy("eurusd_m1_ema_rsi");
    expect(consumeStrategyTarget()).toBe("eurusd_m1_ema_rsi");
    expect(consumeStrategyTarget()).toBeUndefined();
  });

  it("opens the studio without a target", () => {
    navigateTo({ tab: "strategy-studio" });
    expect(consumeStrategyTarget()).toBeUndefined();
  });
});

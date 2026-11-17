import { describe, expect, it } from "vitest";
import {
  EUR_1M_BOT_NAME,
  EUR_1M_STRATEGY_ID,
  EUR_1M_STRATEGY_SPEC,
  EUR_1M_STRATEGY_VERSION,
  EUR_1M_SYMBOL,
  eur1mAutomationInput,
  eur1mPrepareInput,
  eur1mTradingDraft,
} from "./eur-1m";
import { validateTradingDraft } from "./draft";
import { expectedConsentPhrase } from "./draft";

describe("the EUR/USD 1-minute strategy", () => {
  it("is pinned to EURUSD on the engine's 1m timeframe", () => {
    const universe = EUR_1M_STRATEGY_SPEC.universe as { symbols: string[]; asset_classes: string[] };
    const timeframes = EUR_1M_STRATEGY_SPEC.timeframes as { primary: string };
    expect(universe.symbols).toEqual([EUR_1M_SYMBOL]);
    expect(universe.asset_classes).toEqual(["fx"]);
    expect(timeframes.primary).toBe("1m");
    expect(EUR_1M_STRATEGY_SPEC.strategy).toMatchObject({
      id: EUR_1M_STRATEGY_ID,
      version: EUR_1M_STRATEGY_VERSION,
    });
  });

  it("uses a filtered cross and a bracket, not a naked signal", () => {
    const rules = EUR_1M_STRATEGY_SPEC.rules as Record<string, unknown>;
    const entry = rules.entry as { long: { conditions: Array<{ op: string; left: { ref?: string } }> } };
    const exit = rules.exit as { stop_loss: { type: string }; take_profit: { value: number } };
    const refs = entry.long.conditions.map((condition) => condition.left.ref);
    expect(refs).toContain("ema_fast");
    expect(refs).toContain("rsi");
    expect(exit.stop_loss.type).toBe("atr");
    expect(exit.take_profit.value).toBeGreaterThan(0);
  });

  it("models the costs that matter on a 1-minute chart", () => {
    const execution = EUR_1M_STRATEGY_SPEC.execution as Record<string, unknown>;
    expect(execution.fill_at).toBe("next_open");
    expect((execution.spread as { type: string }).type).toBe("bps");
    expect((execution.slippage as { value: number }).value).toBeGreaterThan(0);
  });

  it("sizes by risk and allows both directions", () => {
    const sizing = EUR_1M_STRATEGY_SPEC.position_sizing as { type: string; value: number };
    const risk = EUR_1M_STRATEGY_SPEC.risk as { allow_long: boolean; allow_short: boolean; max_open_positions: number };
    expect(sizing.type).toBe("percent_risk");
    expect(risk.allow_long).toBe(true);
    expect(risk.allow_short).toBe(true);
    expect(risk.max_open_positions).toBe(1);
  });
});

describe("the bot envelope", () => {
  it("starts in shadow on M1 with a London session and a tight leash", () => {
    const draft = eur1mTradingDraft();
    expect(draft.mode).toBe("shadow");
    expect(draft.strategyId).toBe(EUR_1M_STRATEGY_ID);
    expect(draft.symbolsText).toBe("EURUSD");
    expect(draft.timeframe).toBe("M1");
    expect(draft.tier).toBe("l1");
    expect(draft.dryRun).toBe(false);
    expect(draft.sessionEnabled).toBe(true);
    expect(draft.sessionTimezone).toBe("Europe/London");
    expect(draft.sessionStart).toBe("08:00");
    expect(draft.sessionEnd).toBe("17:00");
    expect(draft.sessionWeekdays).toEqual([1, 2, 3, 4, 5]);
    expect(draft.maxOrdersPerDay).toBe(4);
    expect(draft.maxOpenPositions).toBe(1);
    expect(draft.cooldownS).toBe(300);
    expect(draft.requireStop).toBe(true);
    expect(draft.autoMode).toBe(true);
    expect(draft.learningEnabled).toBe(true);
  });

  it("passes the same validation the create dialog uses", () => {
    const { issues, blocked } = validateTradingDraft(
      eur1mTradingDraft(),
      {
        strategies: [
          {
            id: EUR_1M_STRATEGY_ID,
            version: EUR_1M_STRATEGY_VERSION,
            hasBacktest: true,
            approved: true,
          },
        ],
        connections: [],
        venueSymbols: null,
      },
      null,
    );
    expect(issues.filter((issue) => issue.severity === "error")).toEqual([]);
    expect(blocked).toBe(false);
  });

  it("builds the 1-minute automation with the strategy brain and skip-on-misfire", () => {
    const input = eur1mAutomationInput();
    expect(input.name).toBe(EUR_1M_BOT_NAME);
    expect(input.tags).toContain("eur-1m");
    expect(input.trigger).toMatchObject({ type: "interval", intervalSeconds: 60 });
    expect(input.action.type).toBe("run_strategy");
    expect(input.action.objective).toContain("EURUSD");
    const config = input.action.config as Record<string, unknown>;
    expect(config).toMatchObject({
      strategyId: EUR_1M_STRATEGY_ID,
      strategyVersion: EUR_1M_STRATEGY_VERSION,
      mode: "shadow",
      timeframe: "M1",
      symbols: ["EURUSD"],
      maxOrdersPerDay: 4,
    });
    expect(input.execution?.misfire).toBe("skip");
    expect(input.execution?.maxRuntimeS).toBe(120);
    expect(input.executionAuthority).toMatchObject({ tier: "l1", appetite: "normal", requireStop: true });
  });

  it("prepares a shadow trial with no phrase and no venue", () => {
    const prepare = eur1mPrepareInput();
    expect(prepare.mode).toBe("shadow");
    expect(prepare.connectionId).toBe("");
    expect(prepare.confirmation).toBe("");
    expect(prepare.symbols).toEqual(["EURUSD"]);
    expect(prepare.timeframe).toBe("M1");
    expect(prepare.maxOrders).toBe(4);
  });

  it("asks for the demo phrase the server computes", () => {
    expect(expectedConsentPhrase(eur1mTradingDraft(), "MT5 demo")).toBe(
      "MANDATE DEMO MT5 demo",
    );
  });
});

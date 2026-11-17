import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  EUR_1M_BOT_NAME,
  EUR_1M_STRATEGY_ID,
  EUR_1M_STRATEGY_VERSION,
} from "./eur-1m";

const mocks = vi.hoisted(() => ({
  listStrategies: vi.fn(),
  createStrategy: vi.fn(),
  runBacktest: vi.fn(),
  listApprovals: vi.fn(),
  requestApproval: vi.fn(),
  decideApproval: vi.fn(),
  listAutomations: vi.fn(),
  createAutomation: vi.fn(),
  prepareBotTrading: vi.fn(),
  updateAutomation: vi.fn(),
}));

vi.mock("@/lib/backtest/backtest-client", () => ({
  backtestClient: {
    listStrategies: mocks.listStrategies,
    createStrategy: mocks.createStrategy,
    runBacktest: mocks.runBacktest,
    listApprovals: mocks.listApprovals,
    requestApproval: mocks.requestApproval,
    decideApproval: mocks.decideApproval,
  },
}));

vi.mock("@/lib/harness/clients/automation-browser", () => ({
  listAutomations: mocks.listAutomations,
  createAutomation: mocks.createAutomation,
  prepareBotTrading: mocks.prepareBotTrading,
  updateAutomation: mocks.updateAutomation,
}));

import { seedEur1mBot } from "./eur-1m-seed";

function strategy() {
  return {
    id: EUR_1M_STRATEGY_ID,
    name: "EUR/USD 1m EMA-RSI",
    latestVersion: EUR_1M_STRATEGY_VERSION,
    archived: false,
  };
}

function bot(overrides: Record<string, unknown> = {}) {
  return {
    id: "aut_eur",
    name: EUR_1M_BOT_NAME,
    version: 1,
    state: "active",
    action: {
      type: "run_strategy",
      config: {
        strategyId: EUR_1M_STRATEGY_ID,
        strategyVersion: EUR_1M_STRATEGY_VERSION,
        trialId: "live_shadow",
      },
    },
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.listAutomations.mockResolvedValue([]);
  mocks.listStrategies.mockResolvedValue([]);
  mocks.createStrategy.mockResolvedValue({ strategy: strategy(), issues: [] });
  mocks.runBacktest.mockResolvedValue({
    status: "completed",
    metrics: { sharpe: 1.2, totalReturn: 0.04 },
    warnings: [],
  });
  mocks.listApprovals.mockResolvedValue([]);
  mocks.requestApproval.mockResolvedValue({
    id: "appr_1",
    version: EUR_1M_STRATEGY_VERSION,
    status: "pending",
  });
  mocks.decideApproval.mockResolvedValue({
    id: "appr_1",
    version: EUR_1M_STRATEGY_VERSION,
    status: "approved",
  });
  mocks.createAutomation.mockResolvedValue(bot({ state: "draft" }));
  mocks.prepareBotTrading.mockResolvedValue({ trial: { id: "live_shadow" }, automation: bot() });
  mocks.updateAutomation.mockResolvedValue(bot());
});

describe("seeding the EUR/USD 1-minute bot", () => {
  it("creates the strategy, proves it with a backtest, approves, then prepares shadow", async () => {
    const result = await seedEur1mBot();

    expect(mocks.createStrategy).toHaveBeenCalledWith(
      expect.objectContaining({
        strategy: expect.objectContaining({ id: EUR_1M_STRATEGY_ID }),
        universe: { symbols: ["EURUSD"], asset_classes: ["fx"] },
      }),
      expect.any(String),
    );
    expect(mocks.runBacktest).toHaveBeenCalledWith(
      expect.objectContaining({
        strategyId: EUR_1M_STRATEGY_ID,
        symbols: ["EURUSD"],
        save: true,
      }),
    );
    expect(mocks.requestApproval).toHaveBeenCalledTimes(1);
    expect(mocks.decideApproval).toHaveBeenCalledWith("appr_1", true, expect.any(String));

    const created = mocks.createAutomation.mock.calls[0][0];
    expect(created.name).toBe(EUR_1M_BOT_NAME);
    expect(created.state).toBe("draft");
    expect(created.trigger).toMatchObject({ type: "interval", intervalSeconds: 60 });
    expect(created.action.type).toBe("run_strategy");

    const prepare = mocks.prepareBotTrading.mock.calls[0][1];
    expect(prepare).toMatchObject({
      strategyId: EUR_1M_STRATEGY_ID,
      strategyVersion: EUR_1M_STRATEGY_VERSION,
      mode: "shadow",
      confirmation: "",
      timeframe: "M1",
    });
    expect(mocks.updateAutomation).toHaveBeenCalledWith("aut_eur", { state: "active" });
    expect(result.strategyId).toBe(EUR_1M_STRATEGY_ID);
    expect(result.bot.id).toBe("aut_eur");
    expect(result.metrics.sharpe).toBe(1.2);
    expect(result.warnings.join(" ")).toMatch(/shadow/i);
  });

  it("reuses an existing strategy and an approved version", async () => {
    mocks.listStrategies.mockResolvedValue([strategy()]);
    mocks.listApprovals.mockResolvedValue([
      { id: "appr_ok", version: EUR_1M_STRATEGY_VERSION, status: "approved" },
    ]);

    await seedEur1mBot();

    expect(mocks.createStrategy).not.toHaveBeenCalled();
    expect(mocks.requestApproval).not.toHaveBeenCalled();
    expect(mocks.decideApproval).not.toHaveBeenCalled();
  });

  it("is idempotent by bot name", async () => {
    mocks.listAutomations.mockResolvedValue([bot()]);
    const result = await seedEur1mBot();

    expect(mocks.listStrategies).not.toHaveBeenCalled();
    expect(mocks.createAutomation).not.toHaveBeenCalled();
    expect(result.bot.id).toBe("aut_eur");
    expect(result.warnings.join(" ")).toMatch(/already exists/i);
  });

  it("refuses to create a bot on a failed backtest", async () => {
    mocks.runBacktest.mockResolvedValue({
      status: "failed",
      metrics: {},
      warnings: [{ code: "NO_DATA", message: "no EURUSD 1m bars" }],
    });

    await expect(seedEur1mBot()).rejects.toThrow(/backtest could not complete/i);
    expect(mocks.createAutomation).not.toHaveBeenCalled();
  });

  it("leaves a draft and says so when the shadow trial cannot be prepared", async () => {
    mocks.prepareBotTrading.mockRejectedValue(new Error("APPROVAL_REQUIRED"));

    await expect(seedEur1mBot()).rejects.toThrow(/draft/i);
    expect(mocks.updateAutomation).not.toHaveBeenCalled();
  });

  it("surfaces a strategy save failure instead of pretending", async () => {
    mocks.createStrategy.mockRejectedValue(new Error("BAD_PRIMARY_TIMEFRAME"));
    mocks.listStrategies.mockResolvedValue([]);

    await expect(seedEur1mBot()).rejects.toThrow(/BAD_PRIMARY_TIMEFRAME/);
    expect(mocks.runBacktest).not.toHaveBeenCalled();
  });
});

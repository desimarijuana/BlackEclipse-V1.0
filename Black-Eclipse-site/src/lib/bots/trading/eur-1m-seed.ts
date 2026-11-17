"use client";

// ── Seed the EUR/USD 1-minute starter bot ───────────────────────────────────
// One operator action creates the whole vertical:
//   1. the strategy (id `eurusd_m1_ema_rsi`, version 1.0.0) if it is missing;
//   2. a completed 90-day backtest on EURUSD 1m (evidence, not permission);
//   3. an approval for that exact version (recorded as an operator action,
//      shadow-only note — live still needs the tier + arm + consent);
//   4. the automation (a 1-minute schedule, `run_strategy`, L1 leash);
//   5. a SHADOW trial, then activation.
//
// Idempotent by bot name: pressing it twice returns the existing bot. Every
// failure names the gate that blocked it; nothing is fabricated.

import { useCallback, useState } from "react";
import { backtestClient } from "@/lib/backtest/backtest-client";
import {
  createAutomation,
  listAutomations,
  prepareBotTrading,
  updateAutomation,
  type AutomationView,
} from "@/lib/harness/clients/automation-browser";
import { useBotsStore } from "@/lib/bots/bots-store";
import { isBacktestComplete } from "@/lib/strategies/catalog";
import {
  EUR_1M_BOT_NAME,
  EUR_1M_STRATEGY_ID,
  EUR_1M_STRATEGY_SPEC,
  EUR_1M_STRATEGY_VERSION,
  EUR_1M_SYMBOL,
  eur1mAutomationInput,
  eur1mPrepareInput,
} from "./eur-1m";

const DAY_MS = 86_400_000;

export interface Eur1mSeedResult {
  bot: AutomationView;
  strategyId: string;
  strategyVersion: string;
  metrics: Record<string, number | null>;
  warnings: string[];
}

function isoDaysAgo(days: number, from: number = Date.now()): string {
  return new Date(from - days * DAY_MS).toISOString().slice(0, 10);
}

function message(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

export async function seedEur1mBot(): Promise<Eur1mSeedResult> {
  // 1. Idempotent: one bot with this name.
  const existing = await listAutomations();
  const already = existing.find((bot) => bot.name === EUR_1M_BOT_NAME);
  if (already) {
    const config = already.action.config ?? {};
    return {
      bot: already,
      strategyId: String(config.strategyId ?? EUR_1M_STRATEGY_ID),
      strategyVersion: String(config.strategyVersion ?? EUR_1M_STRATEGY_VERSION),
      metrics: {},
      warnings: ["The EUR/USD 1-minute bot already exists."],
    };
  }

  // 2. The strategy. A concurrent seed (or a previous run) may have saved it.
  let strategy = (await backtestClient.listStrategies(true)).find(
    (item) => item.id === EUR_1M_STRATEGY_ID,
  );
  if (!strategy) {
    try {
      const created = await backtestClient.createStrategy(
        EUR_1M_STRATEGY_SPEC,
        "EUR/USD 1-minute starter (EMA cross + RSI veto)",
      );
      strategy = {
        id: created.strategy.id,
        name: created.strategy.name,
        latestVersion: created.strategy.version,
        archived: false,
      };
    } catch (err) {
      strategy = (await backtestClient.listStrategies(true)).find(
        (item) => item.id === EUR_1M_STRATEGY_ID,
      );
      if (!strategy) {
        throw new Error(`The EUR/USD 1m strategy could not be saved: ${message(err)}`);
      }
    }
  }
  const version = strategy.latestVersion || EUR_1M_STRATEGY_VERSION;

  // 3. Evidence: a completed 90-day backtest on 1-minute EURUSD.
  let metrics: Record<string, number | null> = {};
  const warnings: string[] = [];
  try {
    const backtest = await backtestClient.runBacktest({
      strategyId: strategy.id,
      symbols: [EUR_1M_SYMBOL],
      start: isoDaysAgo(90),
      end: isoDaysAgo(0),
      initialCapital: 10_000,
      save: true,
    });
    metrics = backtest.metrics ?? {};
    if (!isBacktestComplete(backtest.status)) {
      throw new Error(
        `the backtest finished as ${backtest.status}${
          backtest.warnings?.length ? ` (${backtest.warnings[0].message})` : ""
        }`,
      );
    }
  } catch (err) {
    throw new Error(
      `The 1-minute EURUSD backtest could not complete, so this bot was not created: ${message(err)}`,
    );
  }

  // 4. Approval for THIS version. Shadow-only; live authority is separate.
  const approvals = await backtestClient.listApprovals(strategy.id);
  const approved = approvals.some(
    (item) => item.version === version && item.status === "approved",
  );
  if (!approved) {
    const pending = approvals.find(
      (item) => item.version === version && item.status !== "approved",
    );
    const request =
      pending ??
      (await backtestClient.requestApproval(
        strategy.id,
        version,
        "EUR/USD 1m starter (shadow execution)",
      ));
    await backtestClient.decideApproval(
      request.id,
      true,
      "EUR/USD 1-minute starter: review recorded for shadow execution only; live still needs L2, an armed connection and standing consent.",
    );
    warnings.push("Strategy version approved for shadow execution by the starter.");
  }

  // 5. The bot, prepared in shadow (never a broker write), then activated.
  let bot = await createAutomation(eur1mAutomationInput(strategy.id, version));
  try {
    const prepared = await prepareBotTrading(bot.id, eur1mPrepareInput(strategy.id, version));
    bot = await updateAutomation(prepared.automation.id, { state: "active" });
  } catch (err) {
    throw new Error(
      `The bot was created as a draft, but its shadow trial could not be prepared: ${message(err)}. Open it and retry.`,
    );
  }
  warnings.push(
    "It runs in shadow on 1-minute bars. Authorize demo (or live) once in its Trading panel to place orders.",
  );

  return { bot, strategyId: strategy.id, strategyVersion: version, metrics, warnings };
}

/** UI hook: seed, refresh the bot list, and open the new bot. */
export function useSeedEur1mBot() {
  const hydrate = useBotsStore((state) => state.hydrate);
  const select = useBotsStore((state) => state.select);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const seed = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const result = await seedEur1mBot();
      await hydrate();
      select(result.bot.id);
      return result;
    } catch (err) {
      setError(message(err));
      return null;
    } finally {
      setBusy(false);
    }
  }, [busy, hydrate, select]);

  return { seed, busy, error };
}

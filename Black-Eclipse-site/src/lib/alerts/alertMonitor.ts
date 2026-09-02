// Alert monitor — server-side poll loop per watch. Loads all active watches
// on boot (like the scraper scheduler), fetches data every intervalSec
// (floor 30s), evaluates the condition tree with edge/cooldown/warmup/one-shot
// gating, dispatches, and persists status for the live UI.
//
// Gating (ant-spam), replicated exactly:
//   EDGE     — fire only on fresh false→true; re-arm when condition goes false
//   COOLDOWN — ≥ cooldownMin between fires on the same symbol
//   WARMUP   — skip evaluation until enough candle history; status 'warming'
//   ONE-SHOT — a poll watch deactivates itself after firing (row survives)

import { prisma } from "@/lib/db";
import { evaluateConditions, describeFire, needsCandles, type ConditionDetail } from "./conditionEvaluator";
import {
  MIN_INTERVAL_SEC,
  fetchSnapshots,
  snapshotWindow,
  updateCandleCache,
  indicatorWindow,
  hasWarmupBars,
  referencedIndicators,
} from "./dataFeeds";
import { dispatchAlert } from "./notifier";

type Logic = "AND" | "OR";

interface WatchRuntime {
  timer: NodeJS.Timeout | null;
  running: boolean; // reentrancy flag
  armed: Map<string, boolean>; // symbol → last condition state (edge gate)
  removed: boolean;
}

const runtimes = new Map<string, WatchRuntime>();
let started = false;

export const HEADLESS_ENV = process.env.BE_HEADLESS_SELFTEST === "1";

export async function startAlertMonitor(): Promise<void> {
  if (started || HEADLESS_ENV) return;
  started = true;
  // Evaluate on the next event-loop tick, not inline — boot must not block.
  setImmediate(() => {
    void loadAndStartAll();
  });
}

async function loadAndStartAll(): Promise<void> {
  try {
    const alerts = await prisma.priceAlert.findMany({ where: { active: true, mode: "poll" } });
    for (const a of alerts) startWatch(a.id);
  } catch (err) {
    console.error("[alert-monitor] load failed:", err);
    started = false;
  }
}

/** Stop a watch's timer (delete/toggle). History rows are never touched. */
export function stopWatch(id: string): void {
  const rt = runtimes.get(id);
  if (rt) {
    rt.removed = true;
    if (rt.timer) clearTimeout(rt.timer);
    runtimes.delete(id);
  }
}

export function isWatchRunning(id: string): boolean {
  return runtimes.has(id);
}

/** (Re)start monitoring for one watch — used on create/edit/toggle/boot. */
export function startWatch(id: string): void {
  if (HEADLESS_ENV) return;
  stopWatch(id);
  const rt: WatchRuntime = { timer: null, running: false, armed: new Map(), removed: false };
  runtimes.set(id, rt);
  const tick = async () => {
    await evaluateOnce(id, rt);
    if (rt.removed) return;
    try {
      const a = await prisma.priceAlert.findUnique({ where: { id }, select: { active: true, intervalSec: true } });
      if (!a || !a.active) {
        runtimes.delete(id);
        return;
      }
      rt.timer = setTimeout(tick, Math.max(MIN_INTERVAL_SEC, a.intervalSec) * 1000);
    } catch {
      rt.timer = setTimeout(tick, MIN_INTERVAL_SEC * 1000);
    }
  };
  rt.timer = setTimeout(tick, 0);
}

async function setStatus(id: string, status: string, msg?: string) {
  try {
    await prisma.priceAlert.update({ where: { id }, data: { status, statusMsg: msg ?? null, lastEvalAt: new Date() } });
  } catch {
    // watch deleted mid-cycle → caller's removed flag handles the no-op
  }
}

/** One poll pass for a watch. Reentrancy-safe: skips if a cycle is running. */
export async function evaluateOnce(id: string, rtIn?: WatchRuntime): Promise<void> {
  const rt = rtIn ?? runtimes.get(id);
  if (rt?.running) return;
  let alert;
  try {
    alert = await prisma.priceAlert.findUnique({ where: { id } });
  } catch {
    return;
  }
  if (!alert || !alert.active || rt?.removed) return;
  if (rt) rt.running = true;

  try {
    const symbols = JSON.parse(alert.symbols) as string[];
    const conditions = JSON.parse(alert.conditions);
    const logic = (alert.logic === "OR" ? "OR" : "AND") as Logic;
    const needsCandleData = needsCandles(conditions);

    // WARMUP: candle watches need cached bars before evaluating.
    if (needsCandleData) {
      const warmed = await Promise.all(
        symbols.map((s) => hasWarmupBars(s, alert.timeframe, conditions))
      );
      if (!warmed.every(Boolean)) {
        await updateCandleCache(alert.market, symbols, alert.timeframe);
        const rewarmed = await Promise.all(
          symbols.map((s) => hasWarmupBars(s, alert.timeframe, conditions))
        );
        if (!rewarmed.every(Boolean)) {
          await setStatus(id, "warming", "collecting candle history");
          return;
        }
      }
    }

    const snaps = await fetchSnapshots(alert.market, symbols);
    if (snaps.size === 0) {
      await setStatus(id, "error", "no snapshot data available");
      return;
    }

    const firedNow: Array<{ symbol: string; details: ConditionDetail[] }> = [];
    const anyError = { v: false };

    for (const [symbol, snap] of snaps) {
      const window = snapshotWindow(snap);
      if (needsCandleData) {
        const iw = await indicatorWindow(symbol, alert.timeframe, conditions);
        for (const [k, v] of iw) window.set(k, v);
      }

      const result = evaluateConditions(conditions, logic as Logic, window);
      if (result.hasError) anyError.v = true;

      const prevArmed = rt?.armed.get(symbol) ?? false; // new watch: prev state unknown → treat as false so an already-true condition fires once
      const edgeOk = !prevArmed; // fresh false→true only
      // Update arm state BEFORE dispatch so a mid-fire removal stays consistent.
      rt?.armed.set(symbol, result.triggered);

      if (!result.triggered || !edgeOk) continue;

      // COOLDOWN
      if (alert.lastFiredAt) {
        const since = Date.now() - alert.lastFiredAt.getTime();
        if (since < alert.cooldownMin * 60000) continue;
      }

      firedNow.push({ symbol, details: result.details });
    }

    if (firedNow.length > 0) {
      for (const f of firedNow) {
        await dispatchAlert({
          alertId: id,
          alertName: alert.name,
          symbols: [f.symbol],
          details: f.details,
        });
      }
      const firedAt = new Date();
      // ONE-SHOT: poll watches deactivate after firing; row + history survive.
      await prisma.priceAlert.update({
        where: { id },
        data: {
          status: "triggered",
          statusMsg: describeFire(firedNow[0].symbol, firedNow[0].details),
          lastFiredAt: firedAt,
          active: false,
        },
      });
      stopWatch(id);
      return;
    }

    await setStatus(
      id,
      anyError.v ? "error" : "watching",
      anyError.v ? "some conditions had non-finite/missing data" : undefined
    );
  } catch (err) {
    await setStatus(id, "error", err instanceof Error ? err.message : String(err));
  } finally {
    if (rt) rt.running = false;
  }
}

/** Which indicator series does a watch need? (exported for UI hints) */
export function watchNeedsCandles(conditions: unknown): boolean {
  return needsCandles(conditions) || referencedIndicators(conditions).some(
    (i) => !["CLOSE", "OPEN", "HIGH", "LOW", "VOLUME", "CHANGE_PCT", "MARKET_CAP", "PE", "EPS", "SECTOR"].includes(i)
  );
}

export function runningWatchCount(): number {
  return runtimes.size;
}
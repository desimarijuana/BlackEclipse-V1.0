// ── Journal demo data — deterministic, clearly-labelled sample trades ────────
// The journal is DB-backed (Prisma), unlike the localStorage portfolio demo, so
// it needs a real server-side seed. This module is the single source of that
// seed: `scripts/seed-journal.ts` and the boot hook both call it.
//
// Three rules make this safe to ship:
//
//   1. **Never overwrite real work.** Seeding only runs when the journal has no
//      trades at all, and every row it creates is tagged `source: 'demo'`.
//   2. **Runs once, ever.** A `SystemConfig` marker records that the seed was
//      attempted, so deleting the demo data does not cause it to reappear on the
//      next boot. (`clearDemoData` + the marker is the opt-out.)
//   3. **Deterministic.** A seeded PRNG means the same demo data every install —
//      reproducible screenshots, no drift, and no fabricated live prices.

import { prisma } from "@/lib/db";
import { getOrCreateProfile, createTrade, countDemoTrades } from "./data";

/** Marks that the demo seed has run (or been deliberately cleared). */
export const DEMO_SEEDED_KEY = "journal_demo_seeded_v1";

const SETUPS = ["BOS + FVG", "Order Block", "Breakout", "Liquidity Sweep", "Trend Continuation"];
const STRATEGIES = [
  { name: "BOS + FVG", markets: ["XAUUSD", "NQ"], confirmation: "15m", entry: "1m", rules: ["Trend confirmed", "BOS", "FVG", "Retracement", "Risk <= 1%", "Minimum 2R"] },
  { name: "Order Block", markets: ["XAUUSD"], confirmation: "1h", entry: "15m", rules: ["HTF order block", "Rejection", "Risk <= 1%"] },
  { name: "Breakout", markets: ["NQ", "BTCUSD"], confirmation: "15m", entry: "5m", rules: ["Range defined", "Volume confirmation", "Risk <= 1%"] },
];

const SYMBOLS = ["XAUUSD", "NQ", "BTCUSD", "EURUSD", "GBPUSD"];
const SESSIONS = ["Asia", "London", "New York"];
const EMOTIONS = ["Calm", "Focused", "Confident", "FOMO", "Revenge", "Bored", "Overconfident"];
const TIMEFRAMES = ["1m", "5m", "15m", "1h"];
const MISTAKES = ["Early exit", "Moved stop", "Moved target", "Partial exit", "Overtraded", "Revenge", "No stop", "Chased entry"];

/** Deterministic PRNG so the seed is reproducible across installs. */
function mulberry32(seed: number) {
  return function () {
    let t = (seed += 0x6d2b79f5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Exported for tests — the PRNG contract is what makes the seed reproducible. */
export const mulberry32Seed = mulberry32;

function pick<T>(rng: () => number, arr: T[]): T {
  return arr[Math.floor(rng() * arr.length)];
}

function rand(rng: () => number, min: number, max: number): number {
  return min + rng() * (max - min);
}

export interface SeedJournalResult {
  seeded: boolean;
  trades: number;
  reason?: string;
}

/**
 * Seed ~90 days of realistic demo trades. Idempotent and conservative:
 *   - skips when the journal already has ANY trade (user data wins),
 *   - skips when the one-time marker is set (so a deliberate clear sticks).
 */
export async function seedJournalDemo(opts: { force?: boolean } = {}): Promise<SeedJournalResult> {
  const profileId = await getOrCreateProfile();

  if (!opts.force) {
    const marker = await prisma.systemConfig.findUnique({ where: { key: DEMO_SEEDED_KEY } });
    if (marker) return { seeded: false, trades: 0, reason: "already seeded (marker set)" };
  }

  const existing = await prisma.trade.count({ where: { profileId } });
  if (existing > 0) {
    // Real (or already-seeded) data exists — never add demo rows on top of it.
    await markSeeded();
    return { seeded: false, trades: 0, reason: `journal already has ${existing} trades` };
  }

  // Size every position off the profile's own risk budget so the demo book is
  // internally coherent: risk per trade lands near the configured fraction of
  // the account, which is what makes the risk analytics (risk consistency, the
  // 1% rule, expectancy in R) meaningful instead of noise from arbitrary
  // quantities. `quantity = riskTarget / stopDistance`.
  const profile = await prisma.journalProfile.findUnique({
    where: { id: profileId },
    select: { accountSize: true, riskPerTrade: true },
  });
  const accountSize = profile?.accountSize && profile.accountSize > 0 ? profile.accountSize : 10_000;
  const riskPerTrade = profile?.riskPerTrade && profile.riskPerTrade > 0 ? profile.riskPerTrade : 0.01;

  const rng = mulberry32(20260909);
  const today = new Date();
  let count = 0;

  // Strategies + setups the demo trades reference.
  const strategyIds: Record<string, string> = {};
  for (const s of STRATEGIES) {
    const created = await prisma.strategy.create({
      data: {
        profileId,
        name: s.name,
        markets: JSON.stringify(s.markets),
        confirmation: s.confirmation,
        entry: s.entry,
        rules: { create: s.rules.map((text) => ({ text })) },
      },
    });
    strategyIds[s.name] = created.id;
  }

  const setupIds: Record<string, string> = {};
  for (const name of SETUPS) {
    const created = await prisma.setup.upsert({
      where: { profileId_name: { profileId, name } },
      update: {},
      create: { profileId, name },
    });
    setupIds[name] = created.id;
  }

  for (let back = 90; back >= 0; back--) {
    const day = new Date(today);
    day.setUTCDate(day.getUTCDate() - back);
    const dow = day.getUTCDay();
    // Mostly weekdays; a few weekend crypto sessions.
    if (dow === 0 || dow === 6) {
      if (rng() > 0.15) continue;
    }
    // Roughly 70% of eligible days have trades, so the calendar has real gaps.
    if (rng() > 0.7) continue;

    const numTrades = 1 + Math.floor(rng() * 3);
    for (let i = 0; i < numTrades; i++) {
      const symbol = pick(rng, SYMBOLS);
      const direction = rng() > 0.5 ? "LONG" : "SHORT";
      const setup = pick(rng, SETUPS);
      const strategy = pick(rng, STRATEGIES).name;
      const session = pick(rng, SESSIONS);
      const emotion = pick(rng, EMOTIONS);
      const timeframe = pick(rng, TIMEFRAMES);

      const base = symbol === "XAUUSD" ? 2650 : symbol === "NQ" ? 20500 : symbol === "BTCUSD" ? 64000 : symbol === "EURUSD" ? 1.09 : 1.27;
      const entry = base * (1 + rand(rng, -0.004, 0.004));
      const stopDist = entry * rand(rng, 0.0015, 0.004);
      const stopLoss = direction === "LONG" ? entry - stopDist : entry + stopDist;
      const targetDist = stopDist * rand(rng, 1.5, 3);
      const takeProfit = direction === "LONG" ? entry + targetDist : entry - targetDist;

      // Risk a lightly-varying fraction of the budget (0.7–1.0×) so risk
      // consistency is a real signal rather than a constant 100%.
      const riskTarget = accountSize * riskPerTrade * rand(rng, 0.7, 1.0);
      const quantity = riskTarget / stopDist;

      // 55% base win rate, shifted by the recorded emotion (Calm/Focused help,
      // FOMO/Revenge/Bored hurt). Across the emotion mix that lands near ~49% in
      // practice, which is realistic — and gives the psychology view a genuine
      // signal to find rather than uniform noise. With ~2R winners vs −1R losers
      // the book still has positive expectancy.
      const emotionBias = emotion === "FOMO" || emotion === "Revenge" || emotion === "Bored" ? -0.25
        : emotion === "Calm" || emotion === "Focused" ? 0.15 : 0;
      const winChance = Math.min(0.9, Math.max(0.1, 0.55 + emotionBias));
      const won = rng() < winChance;

      // Winners land between +0.9R and +3R (partial→full target); losers between
      // −0.8R and −1.2R (stop with a little slippage).
      const exit = won
        ? direction === "LONG"
          ? entry + targetDist * rand(rng, 0.6, 1.0)
          : entry - targetDist * rand(rng, 0.6, 1.0)
        : direction === "LONG"
          ? entry - stopDist * rand(rng, 0.8, 1.2)
          : entry + stopDist * rand(rng, 0.8, 1.2);

      const hour = session === "Asia" ? 3 + Math.floor(rng() * 4)
        : session === "London" ? 8 + Math.floor(rng() * 4)
        : 13 + Math.floor(rng() * 4);
      const minute = Math.floor(rng() * 60);
      const entryTime = new Date(day);
      entryTime.setUTCHours(hour, minute, 0, 0);
      const exitTime = new Date(entryTime.getTime() + (15 + Math.floor(rng() * 120)) * 60000);

      const mistakes = won && rng() < 0.2 ? [pick(rng, MISTAKES)]
        : !won && rng() < 0.5 ? [pick(rng, MISTAKES)]
        : [];

      await createTrade(profileId, {
        symbol,
        direction,
        entry,
        exit,
        stopLoss,
        takeProfit,
        quantity,
        entryTime: entryTime.toISOString(),
        exitTime: exitTime.toISOString(),
        timeframe,
        session,
        marketRegime: rng() > 0.5 ? "Trending" : "Ranging",
        trend: direction === "LONG" ? "Bullish" : "Bearish",
        confluences: 1 + Math.floor(rng() * 3),
        emotion,
        confidence: 2 + Math.floor(rng() * 4),
        mistakes,
        notes: won ? "Followed the plan." : "Setup was valid but timing was off.",
        strategyId: strategyIds[strategy],
        setupId: setupIds[setup],
        tagNames: mistakes.length > 0 ? mistakes : [],
        source: "demo",
      });
      count++;
    }
  }

  await markSeeded();
  return { seeded: true, trades: count };
}

async function markSeeded(): Promise<void> {
  try {
    await prisma.systemConfig.upsert({
      where: { key: DEMO_SEEDED_KEY },
      update: { value: new Date().toISOString() },
      create: { key: DEMO_SEEDED_KEY, value: new Date().toISOString() },
    });
  } catch { /* best-effort — a missing marker only risks a re-seed attempt */ }
}

/** True when the profile currently holds only the seeded demo trades. */
export async function hasOnlyDemoData(profileId: string): Promise<boolean> {
  const [total, demo] = await Promise.all([
    prisma.trade.count({ where: { profileId } }),
    countDemoTrades(profileId),
  ]);
  return demo > 0 && demo === total;
}

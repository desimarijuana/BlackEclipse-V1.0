// ── Journal seed — populate the journal with realistic demo data ─────────────
// Run: npx tsx scripts/seed-journal.ts
// Idempotent: only seeds when the journal is empty.

import { prisma } from "../src/lib/db";
import { getOrCreateProfile, createTrade } from "../src/lib/journal/data";

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

// Deterministic pseudo-random so the seed is reproducible.
function mulberry32(seed: number) {
  return function () {
    let t = (seed += 0x6d2b79f5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function pick<T>(rng: () => number, arr: T[]): T {
  return arr[Math.floor(rng() * arr.length)];
}

function rand(rng: () => number, min: number, max: number): number {
  return min + rng() * (max - min);
}

async function main() {
  const profileId = await getOrCreateProfile();

  const existing = await prisma.trade.count({ where: { profileId } });
  if (existing > 0) {
    console.log(`Journal already has ${existing} trades — skipping seed.`);
    return;
  }

  // Create strategies + setups.
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

  // Seed ~90 days of trades ending today, ~2-4 trades/day on weekdays.
  const rng = mulberry32(20260909);
  const today = new Date();
  let count = 0;

  for (let back = 90; back >= 0; back--) {
    const day = new Date(today);
    day.setUTCDate(day.getUTCDate() - back);
    const dow = day.getUTCDay();
    // Skip weekends mostly (occasional weekend crypto trade).
    if (dow === 0 || dow === 6) {
      if (rng() > 0.15) continue;
    }
    // ~70% of weekdays have trades.
    if (rng() > 0.7) continue;

    const numTrades = 1 + Math.floor(rng() * 3); // 1-3 trades
    for (let i = 0; i < numTrades; i++) {
      const symbol = pick(rng, SYMBOLS);
      const direction = rng() > 0.5 ? "LONG" : "SHORT";
      const setup = pick(rng, SETUPS);
      const strategy = pick(rng, STRATEGIES).name;
      const session = pick(rng, SESSIONS);
      const emotion = pick(rng, EMOTIONS);
      const timeframe = pick(rng, TIMEFRAMES);

      // Base price per symbol.
      const base = symbol === "XAUUSD" ? 2650 : symbol === "NQ" ? 20500 : symbol === "BTCUSD" ? 64000 : symbol === "EURUSD" ? 1.09 : 1.27;
      const entry = base * (1 + rand(rng, -0.004, 0.004));
      const stopDist = entry * rand(rng, 0.0015, 0.004);
      const stopLoss = direction === "LONG" ? entry - stopDist : entry + stopDist;
      const targetDist = stopDist * rand(rng, 1.5, 3);
      const takeProfit = direction === "LONG" ? entry + targetDist : entry - targetDist;

      // Outcome: ~55% win, weighted by emotion.
      const emotionBias = emotion === "FOMO" || emotion === "Revenge" || emotion === "Bored" ? -0.25 : emotion === "Calm" || emotion === "Focused" ? 0.15 : 0;
      const winChance = Math.min(0.9, Math.max(0.1, 0.55 + emotionBias));
      const won = rng() < winChance;

      // Exit: winners near target, losers near stop.
      const exit = won
        ? direction === "LONG"
          ? entry + targetDist * rand(rng, 0.6, 1.0)
          : entry - targetDist * rand(rng, 0.6, 1.0)
        : direction === "LONG"
          ? entry - stopDist * rand(rng, 0.8, 1.2)
          : entry + stopDist * rand(rng, 0.8, 1.2);

      const quantity = symbol === "XAUUSD" ? 1 : symbol === "NQ" ? 1 : symbol === "BTCUSD" ? 0.1 : 10000;

      const hour = session === "Asia" ? 3 + Math.floor(rng() * 4) : session === "London" ? 8 + Math.floor(rng() * 4) : 13 + Math.floor(rng() * 4);
      const minute = Math.floor(rng() * 60);
      const entryTime = new Date(day);
      entryTime.setUTCHours(hour, minute, 0, 0);
      const exitTime = new Date(entryTime.getTime() + (15 + Math.floor(rng() * 120)) * 60000);

      const mistakes = won && rng() < 0.2 ? [pick(rng, MISTAKES)] : !won && rng() < 0.5 ? [pick(rng, MISTAKES)] : [];

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
      });
      count++;
    }
  }

  console.log(`Seeded ${count} demo trades.`);
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });

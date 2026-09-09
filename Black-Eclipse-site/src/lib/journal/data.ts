// ── Journal data access — server-side Prisma helpers ─────────────────────────
// Maps Prisma Trade rows to the analytics TradeRecord shape and provides the
// CRUD operations used by the API routes. All business math lives in the
// analytics engine; this layer only persists and reads.

import { prisma } from "@/lib/db";
import { computeTradeMath } from "./trade-math";
import type { TradeRecord } from "./types";

/** The single guest profile id. Creates it on first use. */
export async function getOrCreateProfile(): Promise<string> {
  const existing = await prisma.journalProfile.findFirst();
  if (existing) return existing.id;
  const created = await prisma.journalProfile.create({ data: {} });
  return created.id;
}

/** Map a Prisma trade (with relations) to the analytics TradeRecord. */
export function toTradeRecord(t: {
  id: string;
  symbol: string;
  direction: string;
  entry: number;
  exit: number;
  stopLoss: number | null;
  takeProfit: number | null;
  quantity: number;
  entryTime: Date;
  exitTime: Date;
  timeframe: string | null;
  session: string | null;
  marketRegime: string | null;
  trend: string | null;
  confluences: number | null;
  emotion: string | null;
  confidence: number | null;
  mistakes: string | null;
  notes: string | null;
  status: string;
  strategyId: string | null;
  setupId: string | null;
  pnl: number;
  pnlPct: number;
  rMultiple: number;
  riskAmount: number | null;
  rewardAmount: number | null;
  actualRR: number | null;
  durationSec: number | null;
  mfe: number | null;
  mae: number | null;
  strategy?: { name: string } | null;
  setup?: { name: string } | null;
  tags?: { tag: { name: string } }[];
}): TradeRecord {
  return {
    id: t.id,
    symbol: t.symbol,
    direction: t.direction as TradeRecord["direction"],
    entry: t.entry,
    exit: t.exit,
    stopLoss: t.stopLoss,
    takeProfit: t.takeProfit,
    quantity: t.quantity,
    entryTime: t.entryTime.toISOString(),
    exitTime: t.exitTime.toISOString(),
    timeframe: t.timeframe,
    session: t.session,
    marketRegime: t.marketRegime,
    trend: t.trend,
    confluences: t.confluences,
    emotion: t.emotion,
    confidence: t.confidence,
    mistakes: t.mistakes,
    notes: t.notes,
    status: t.status as TradeRecord["status"],
    strategyId: t.strategyId,
    strategyName: t.strategy?.name,
    setupId: t.setupId,
    setupName: t.setup?.name,
    tags: t.tags?.map((tt) => tt.tag.name),
    pnl: t.pnl,
    pnlPct: t.pnlPct,
    rMultiple: t.rMultiple,
    riskAmount: t.riskAmount,
    rewardAmount: t.rewardAmount,
    actualRR: t.actualRR,
    durationSec: t.durationSec,
    mfe: t.mfe,
    mae: t.mae,
  };
}

const tradeInclude = {
  strategy: { select: { name: true } },
  setup: { select: { name: true } },
  tags: { include: { tag: { select: { name: true } } } },
} as const;

/** Load all closed trades for a profile as TradeRecords. */
export async function loadTrades(profileId: string): Promise<TradeRecord[]> {
  const rows = await prisma.trade.findMany({
    where: { profileId },
    include: tradeInclude,
    orderBy: { entryTime: "asc" },
  });
  return rows.map(toTradeRecord);
}

export interface CreateTradeInput {
  symbol: string;
  direction: "LONG" | "SHORT";
  entry: number;
  exit: number;
  stopLoss?: number | null;
  takeProfit?: number | null;
  quantity: number;
  entryTime: string;
  exitTime: string;
  timeframe?: string | null;
  session?: string | null;
  marketRegime?: string | null;
  trend?: string | null;
  confluences?: number | null;
  emotion?: string | null;
  confidence?: number | null;
  mistakes?: string[] | null;
  notes?: string | null;
  strategyId?: string | null;
  setupId?: string | null;
  tagNames?: string[];
}

/** Create a trade, computing all derived metrics and linking the day. */
export async function createTrade(profileId: string, input: CreateTradeInput) {
  const math = computeTradeMath({
    direction: input.direction,
    entry: input.entry,
    exit: input.exit,
    stopLoss: input.stopLoss ?? null,
    takeProfit: input.takeProfit ?? null,
    quantity: input.quantity,
    entryTime: input.entryTime,
    exitTime: input.exitTime,
  });

  const dayDate = new Date(input.exitTime.slice(0, 10) + "T00:00:00Z");
  const day = await prisma.journalDay.upsert({
    where: { profileId_date: { profileId, date: dayDate } },
    update: {},
    create: { profileId, date: dayDate },
  });

  const trade = await prisma.trade.create({
    data: {
      profileId,
      symbol: input.symbol.toUpperCase(),
      direction: input.direction,
      entry: input.entry,
      exit: input.exit,
      stopLoss: input.stopLoss ?? null,
      takeProfit: input.takeProfit ?? null,
      quantity: input.quantity,
      entryTime: new Date(input.entryTime),
      exitTime: new Date(input.exitTime),
      timeframe: input.timeframe ?? null,
      session: input.session ?? null,
      marketRegime: input.marketRegime ?? null,
      trend: input.trend ?? null,
      confluences: input.confluences ?? null,
      emotion: input.emotion ?? null,
      confidence: input.confidence ?? null,
      mistakes: input.mistakes ? JSON.stringify(input.mistakes) : null,
      notes: input.notes ?? null,
      strategyId: input.strategyId ?? null,
      setupId: input.setupId ?? null,
      dayId: day.id,
      pnl: math.pnl,
      pnlPct: math.pnlPct,
      rMultiple: math.rMultiple,
      riskAmount: math.riskAmount,
      rewardAmount: math.rewardAmount,
      actualRR: math.actualRR,
      durationSec: math.durationSec,
      mfe: null,
      mae: null,
      executions: {
        create: { kind: "created", detail: JSON.stringify({ entry: input.entry, exit: input.exit }) },
      },
      tags: input.tagNames?.length
        ? {
            create: input.tagNames.map((name) => ({
              tag: { connectOrCreate: { where: { profileId_name: { profileId, name } }, create: { profileId, name } } },
            })),
          }
        : undefined,
    },
    include: tradeInclude,
  });

  return toTradeRecord(trade);
}

/** Delete a trade. */
export async function deleteTrade(profileId: string, tradeId: string): Promise<boolean> {
  const result = await prisma.trade.deleteMany({ where: { id: tradeId, profileId } });
  return result.count > 0;
}

/** List strategies for a profile. */
export async function listStrategies(profileId: string) {
  return prisma.strategy.findMany({
    where: { profileId },
    include: { rules: true },
    orderBy: { createdAt: "asc" },
  });
}

/** List setups for a profile. */
export async function listSetups(profileId: string) {
  return prisma.setup.findMany({ where: { profileId }, orderBy: { name: "asc" } });
}

/** List tags for a profile. */
export async function listTags(profileId: string) {
  return prisma.tag.findMany({ where: { profileId }, orderBy: { name: "asc" } });
}

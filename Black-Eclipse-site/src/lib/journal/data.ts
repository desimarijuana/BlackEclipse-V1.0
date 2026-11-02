// ── Journal data access — server-side Prisma helpers ─────────────────────────
// Maps Prisma Trade rows to the analytics TradeRecord shape and provides the
// CRUD operations used by the API routes. All business math lives in the
// analytics engine; this layer only persists and reads.

import { prisma } from "@/lib/db";
import { computeTradeMath } from "./trade-math";
import type { TradeRecord } from "./types";

/**
 * The single guest profile id. Creates it on first use.
 *
 * Concurrent callers used to race here: two requests both saw no profile and
 * both created one, leaving duplicate "Trader" rows (which is exactly what the
 * committed DB ended up with). The lookup is now deterministic — always the
 * OLDEST row — and creating is guarded so a duplicate is collapsed on sight.
 */
export async function getOrCreateProfile(): Promise<string> {
  const existing = await prisma.journalProfile.findFirst({
    orderBy: { createdAt: "asc" },
  });
  if (existing) {
    // Collapse any duplicates a previous race left behind. Cascades clean up
    // their relations; since the survivor is the oldest, nothing the user
    // created is lost.
    const dupes = await prisma.journalProfile.findMany({
      where: { id: { not: existing.id } },
      select: { id: true },
    });
    if (dupes.length > 0) {
      await prisma.journalProfile.deleteMany({ where: { id: { in: dupes.map(d => d.id) } } });
    }
    return existing.id;
  }
  const created = await prisma.journalProfile.create({ data: {} });
  return created.id;
}

/** How many seeded demo trades exist for a profile. */
export async function countDemoTrades(profileId: string): Promise<number> {
  return prisma.trade.count({ where: { profileId, source: "demo" } });
}

/**
 * Remove every seeded demo trade (and its strategies/setups/tags/reviews).
 * Only touches `source: 'demo'` rows — anything the user entered is untouched.
 */
export async function clearDemoData(profileId: string): Promise<{ trades: number }> {
  const trades = await prisma.trade.count({ where: { profileId, source: "demo" } });
  if (trades === 0) return { trades: 0 };
  // Trade relations cascade from the trade delete except the explicit joins.
  await prisma.trade.deleteMany({ where: { profileId, source: "demo" } });
  // Demo-created scaffolding hangs off the profile and is only ever created by
  // the seeder; drop it so a re-seed starts clean.
  await prisma.journalDay.deleteMany({ where: { profileId } });
  await prisma.strategy.deleteMany({ where: { profileId } });
  await prisma.setup.deleteMany({ where: { profileId } });
  await prisma.tag.deleteMany({ where: { profileId } });
  await prisma.review.deleteMany({ where: { profileId, source: "demo" } });
  return { trades };
}

/** Map a Prisma trade (with relations) to the analytics TradeRecord. */
export function toTradeRecord(t: {
  id: string;
  symbol: string;
  direction: string;
  entry: number;
  exit: number | null;
  stopLoss: number | null;
  takeProfit: number | null;
  quantity: number;
  entryTime: Date;
  exitTime: Date | null;
  timeframe: string | null;
  session: string | null;
  marketRegime: string | null;
  trend: string | null;
  confluences: number | null;
  emotion: string | null;
  confidence: number | null;
  mistakes: string | null;
  notes: string | null;
  grade?: string | null;
  checklist?: string | null;
  status: string;
  source?: string | null;
  externalId?: string | null;
  brokerConnectionId?: string | null;
  brokerPositionTicket?: number | null;
  pnlBasis?: string | null;
  ignoredAt?: Date | null;
  accountId?: string | null;
  strategyId: string | null;
  setupId: string | null;
  grossPnl?: number | null;
  commission?: number | null;
  fee?: number | null;
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
  account?: { name: string } | null;
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
    exitTime: (t.exitTime ?? t.entryTime).toISOString(),
    timeframe: t.timeframe,
    session: t.session,
    marketRegime: t.marketRegime,
    trend: t.trend,
    confluences: t.confluences,
    emotion: t.emotion,
    confidence: t.confidence,
    mistakes: t.mistakes,
    notes: t.notes,
    grade: t.grade ?? null,
    checklist: t.checklist ?? null,
    status: t.status as TradeRecord["status"],
    source: (t.source === "demo" || t.source === "broker" ? t.source : "manual") as TradeRecord["source"],
    externalId: t.externalId ?? null,
    brokerConnectionId: t.brokerConnectionId ?? null,
    brokerPositionTicket: t.brokerPositionTicket ?? null,
    pnlBasis: t.pnlBasis === "broker" ? "broker" : "computed",
    strategyId: t.strategyId,
    strategyName: t.strategy?.name,
    setupId: t.setupId,
    setupName: t.setup?.name,
    accountId: t.accountId ?? null,
    accountName: t.account?.name,
    tags: t.tags?.map((tt) => tt.tag.name),
    grossPnl: t.grossPnl ?? t.pnl,
    commission: t.commission ?? 0,
    fee: t.fee ?? 0,
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
  account: { select: { name: true } },
  tags: { include: { tag: { select: { name: true } } } },
  marketContext: true,
} as const;

/** Load all closed trades for a profile as TradeRecords. */
export async function loadTrades(profileId: string): Promise<TradeRecord[]> {
  const rows = await prisma.trade.findMany({
    // A broker-sourced trade the user explicitly deleted is ignored, not
    // re-projected: `ignoredAt` is a tombstone for its externalId.
    where: { profileId, ignoredAt: null },
    include: tradeInclude,
    orderBy: { entryTime: "asc" },
  });
  return rows.map(toTradeRecord);
}

export interface CreateTradeInput {
  symbol: string;
  direction: "LONG" | "SHORT";
  entry: number;
  /** Null/omitted → the position is open (no exit yet). */
  exit?: number | null;
  stopLoss?: number | null;
  takeProfit?: number | null;
  quantity: number;
  entryTime: string;
  /** Required when `exit` is set; ignored for open positions. */
  exitTime?: string | null;
  timeframe?: string | null;
  session?: string | null;
  marketRegime?: string | null;
  trend?: string | null;
  confluences?: number | null;
  emotion?: string | null;
  confidence?: number | null;
  mistakes?: string[] | null;
  notes?: string | null;
  grade?: string | null;
  checklist?: Record<string, boolean> | null;
  strategyId?: string | null;
  setupId?: string | null;
  accountId?: string | null;
  tagNames?: string[];
  commission?: number | null;
  fee?: number | null;
  /** Explicit status override. Defaults from whether an exit is present. */
  status?: "open" | "closed";
  /** Provenance. Defaults to 'manual'; the demo seeder passes 'demo'. */
  source?: "manual" | "demo";
}

/** Create a trade, computing all derived metrics and linking the day. */
export async function createTrade(profileId: string, input: CreateTradeInput) {
  const isOpen = input.status === "open" || input.exit == null;
  const effectiveExit = isOpen ? null : (input.exit as number);
  const effectiveExitTime = isOpen ? input.entryTime : (input.exitTime ?? input.entryTime);
  const math = computeTradeMath({
    direction: input.direction,
    entry: input.entry,
    exit: effectiveExit,
    stopLoss: input.stopLoss ?? null,
    takeProfit: input.takeProfit ?? null,
    quantity: input.quantity,
    entryTime: input.entryTime,
    exitTime: effectiveExitTime,
    commission: input.commission ?? 0,
    fee: input.fee ?? 0,
  });

  const dayDate = new Date(effectiveExitTime.slice(0, 10) + "T00:00:00Z");
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
      exit: effectiveExit,
      stopLoss: input.stopLoss ?? null,
      takeProfit: input.takeProfit ?? null,
      quantity: input.quantity,
      entryTime: new Date(input.entryTime),
      exitTime: isOpen ? null : new Date(effectiveExitTime),
      timeframe: input.timeframe ?? null,
      session: input.session ?? null,
      marketRegime: input.marketRegime ?? null,
      trend: input.trend ?? null,
      confluences: input.confluences ?? null,
      emotion: input.emotion ?? null,
      confidence: input.confidence ?? null,
      mistakes: input.mistakes ? JSON.stringify(input.mistakes) : null,
      notes: input.notes ?? null,
      grade: input.grade ?? null,
      checklist: input.checklist ? JSON.stringify(input.checklist) : null,
      strategyId: input.strategyId ?? null,
      setupId: input.setupId ?? null,
      accountId: input.accountId ?? null,
      status: isOpen ? "open" : "closed",
      source: input.source ?? "manual",
      dayId: day.id,
      grossPnl: math.grossPnl,
      commission: input.commission ?? 0,
      fee: input.fee ?? 0,
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

/**
 * Delete a trade.
 *
 * A broker-sourced trade is tombstoned instead of destroyed: the next sync
 * would otherwise recreate it from the broker's history. `ignoredAt` keeps the
 * externalId out of every read while leaving the audit trail intact.
 */
export async function deleteTrade(profileId: string, tradeId: string): Promise<boolean> {
  const trade = await prisma.trade.findFirst({
    where: { id: tradeId, profileId },
    select: { id: true, source: true },
  });
  if (!trade) return false;
  if (trade.source === "broker") {
    await prisma.trade.update({ where: { id: trade.id }, data: { ignoredAt: new Date() } });
    return true;
  }
  const result = await prisma.trade.deleteMany({ where: { id: tradeId, profileId } });
  return result.count > 0;
}

export interface UpdateTradeInput {
  symbol?: string;
  direction?: "LONG" | "SHORT";
  entry?: number;
  /** Null closes-to-open (reopens the position). */
  exit?: number | null;
  stopLoss?: number | null;
  takeProfit?: number | null;
  quantity?: number;
  entryTime?: string;
  exitTime?: string | null;
  timeframe?: string | null;
  session?: string | null;
  marketRegime?: string | null;
  trend?: string | null;
  confluences?: number | null;
  emotion?: string | null;
  confidence?: number | null;
  mistakes?: string[] | null;
  notes?: string | null;
  grade?: string | null;
  checklist?: Record<string, boolean> | null;
  strategyId?: string | null;
  setupId?: string | null;
  accountId?: string | null;
  tagNames?: string[];
  commission?: number | null;
  fee?: number | null;
  /** Execution event kind to log (e.g. 'entry_modified', 'stop_modified', 'closed'). */
  eventKind?: string;
}

/**
 * Update a trade, recomputing derived metrics and appending an execution event.
 * Returns the updated TradeRecord, or null if the trade isn't found.
 */
export async function updateTrade(profileId: string, tradeId: string, input: UpdateTradeInput) {
  const existing = await prisma.trade.findFirst({ where: { id: tradeId, profileId } });
  if (!existing) return null;

  const nextExit = input.exit !== undefined ? input.exit : existing.exit;
  const providedExitTime = input.exitTime !== undefined
    ? (input.exitTime ? new Date(input.exitTime) : null)
    : existing.exitTime;
  const isOpen = nextExit == null;
  const nextExitTime = isOpen ? null : providedExitTime;

  const next = {
    symbol: input.symbol?.toUpperCase() ?? existing.symbol,
    direction: input.direction ?? existing.direction,
    entry: input.entry ?? existing.entry,
    exit: isOpen ? null : nextExit,
    stopLoss: input.stopLoss !== undefined ? input.stopLoss : existing.stopLoss,
    takeProfit: input.takeProfit !== undefined ? input.takeProfit : existing.takeProfit,
    quantity: input.quantity ?? existing.quantity,
    entryTime: input.entryTime ? new Date(input.entryTime) : existing.entryTime,
    exitTime: nextExitTime,
    timeframe: input.timeframe !== undefined ? input.timeframe : existing.timeframe,
    session: input.session !== undefined ? input.session : existing.session,
    marketRegime: input.marketRegime !== undefined ? input.marketRegime : existing.marketRegime,
    trend: input.trend !== undefined ? input.trend : existing.trend,
    confluences: input.confluences !== undefined ? input.confluences : existing.confluences,
    emotion: input.emotion !== undefined ? input.emotion : existing.emotion,
    confidence: input.confidence !== undefined ? input.confidence : existing.confidence,
    mistakes: input.mistakes !== undefined ? JSON.stringify(input.mistakes) : existing.mistakes,
    notes: input.notes !== undefined ? input.notes : existing.notes,
    grade: input.grade !== undefined ? input.grade : existing.grade,
    checklist: input.checklist !== undefined ? JSON.stringify(input.checklist) : existing.checklist,
    strategyId: input.strategyId !== undefined ? input.strategyId : existing.strategyId,
    setupId: input.setupId !== undefined ? input.setupId : existing.setupId,
    accountId: input.accountId !== undefined ? input.accountId : existing.accountId,
    commission: input.commission !== undefined ? (input.commission ?? 0) : existing.commission,
    fee: input.fee !== undefined ? (input.fee ?? 0) : existing.fee,
    status: isOpen ? "open" : "closed",
  };

  // Recompute derived metrics from the merged values.
  const math = computeTradeMath({
    direction: next.direction as "LONG" | "SHORT",
    entry: next.entry,
    exit: next.exit,
    stopLoss: next.stopLoss,
    takeProfit: next.takeProfit,
    quantity: next.quantity,
    entryTime: next.entryTime.toISOString(),
    exitTime: (next.exitTime ?? next.entryTime).toISOString(),
    commission: next.commission,
    fee: next.fee,
  });

  const updated = await prisma.trade.update({
    where: { id: tradeId },
    data: {
      ...next,
      grossPnl: math.grossPnl,
      pnl: math.pnl,
      pnlPct: math.pnlPct,
      rMultiple: math.rMultiple,
      riskAmount: math.riskAmount,
      rewardAmount: math.rewardAmount,
      actualRR: math.actualRR,
      durationSec: math.durationSec,
      executions: {
        create: {
          kind: input.eventKind ?? "updated",
          detail: JSON.stringify({ entry: next.entry, exit: next.exit, stopLoss: next.stopLoss }),
        },
      },
      tags: input.tagNames
        ? {
            deleteMany: {},
            create: input.tagNames.map((name) => ({
              tag: { connectOrCreate: { where: { profileId_name: { profileId, name } }, create: { profileId, name } } },
            })),
          }
        : undefined,
    },
    include: tradeInclude,
  });

  return toTradeRecord(updated);
}

export interface SaveMarketContextInput {
  trend?: string | null;
  vwap?: string | null;
  ema50AboveEma200?: boolean | null;
  adx?: number | null;
  atr?: number | null;
  regime?: string | null;
  volatility?: string | null;
  session?: string | null;
  raw?: string | null;
}

/** Upsert market context for a trade. */
export async function saveMarketContext(profileId: string, tradeId: string, input: SaveMarketContextInput) {
  const trade = await prisma.trade.findFirst({ where: { id: tradeId, profileId }, select: { id: true } });
  if (!trade) return null;
  return prisma.marketContext.upsert({
    where: { tradeId },
    update: input,
    create: { tradeId, ...input },
  });
}

/** Update a trade's MFE/MAE values. */
export async function updateTradeMfeMae(profileId: string, tradeId: string, mfe: number | null, mae: number | null) {
  const trade = await prisma.trade.findFirst({ where: { id: tradeId, profileId }, select: { id: true } });
  if (!trade) return null;
  return prisma.trade.update({ where: { id: tradeId }, data: { mfe, mae } });
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

/** Bulk-import trades from parsed CSV rows. Returns { imported, errors }. */
export async function bulkImportTrades(profileId: string, rows: CreateTradeInput[]): Promise<{ imported: number; errors: string[] }> {
  let imported = 0;
  const errors: string[] = [];
  for (let i = 0; i < rows.length; i++) {
    const row = rows[i];
    try {
      if (!row.symbol || !row.entry || !row.exit || !row.entryTime || !row.exitTime) {
        errors.push(`Row ${i + 1}: missing required fields (symbol, entry, exit, entryTime, exitTime)`);
        continue;
      }
      await createTrade(profileId, row);
      imported++;
    } catch (e) {
      errors.push(`Row ${i + 1}: ${e instanceof Error ? e.message : "failed to import"}`);
    }
  }
  return { imported, errors };
}

/** Add a screenshot to a trade. */
export async function addTradeScreenshot(profileId: string, tradeId: string, url: string, phase?: string | null, caption?: string | null) {
  const trade = await prisma.trade.findFirst({ where: { id: tradeId, profileId }, select: { id: true } });
  if (!trade) return null;
  return prisma.tradeScreenshot.create({
    data: { tradeId, url, phase: phase ?? null, caption: caption ?? null },
  });
}

/** List screenshots for a trade. */
export async function listTradeScreenshots(profileId: string, tradeId: string) {
  const trade = await prisma.trade.findFirst({ where: { id: tradeId, profileId }, select: { id: true } });
  if (!trade) return [];
  return prisma.tradeScreenshot.findMany({ where: { tradeId }, orderBy: { createdAt: "asc" } });
}

/** Delete a screenshot. */
export async function deleteTradeScreenshot(profileId: string, screenshotId: string): Promise<boolean> {
  const shot = await prisma.tradeScreenshot.findUnique({ where: { id: screenshotId } });
  if (!shot) return false;
  const trade = await prisma.trade.findFirst({ where: { id: shot.tradeId, profileId }, select: { id: true } });
  if (!trade) return false;
  await prisma.tradeScreenshot.delete({ where: { id: screenshotId } });
  return true;
}

/** Persist an AI-generated review. */
export async function saveAiReview(profileId: string, input: {
  kind: string;
  title: string;
  body: string;
  tradeId?: string | null;
  periodStart?: string | null;
  periodEnd?: string | null;
}) {
  return prisma.review.create({
    data: {
      profileId,
      kind: input.kind,
      title: input.title,
      body: input.body,
      tradeId: input.tradeId ?? null,
      periodStart: input.periodStart ? new Date(input.periodStart + "T00:00:00Z") : null,
      periodEnd: input.periodEnd ? new Date(input.periodEnd + "T00:00:00Z") : null,
      source: "ai",
    },
  });
}

// ── Profile (settings vault) ─────────────────────────────────────────────────

/** Read the guest profile (settings: name, currency, risk, account size). */
export async function getProfile(profileId: string) {
  return prisma.journalProfile.findUnique({ where: { id: profileId } });
}

export interface UpdateProfileInput {
  name?: string;
  currency?: string;
  riskPerTrade?: number;
  accountSize?: number;
}

/** Update the trader's settings. Only provided fields change. */
export async function updateProfile(profileId: string, input: UpdateProfileInput) {
  return prisma.journalProfile.update({ where: { id: profileId }, data: input });
}

// ── Trading accounts (multi-account support) ─────────────────────────────────

export interface AccountInput {
  name: string;
  broker?: string | null;
  currency?: string;
  initialBalance?: number;
}

/** List a profile's trading accounts (oldest first). */
export async function listAccounts(profileId: string) {
  return prisma.tradingAccount.findMany({
    where: { profileId },
    orderBy: { createdAt: "asc" },
  });
}

/** Create a trading account. */
export async function createAccount(profileId: string, input: AccountInput) {
  return prisma.tradingAccount.create({
    data: {
      profileId,
      name: input.name,
      broker: input.broker ?? null,
      currency: input.currency ?? "USD",
      initialBalance: input.initialBalance ?? 0,
    },
  });
}

export interface UpdateAccountInput {
  name?: string;
  broker?: string | null;
  currency?: string;
  initialBalance?: number;
  archived?: boolean;
}

/** Update a trading account. Returns null when not found (or wrong profile). */
export async function updateAccount(profileId: string, accountId: string, input: UpdateAccountInput) {
  const existing = await prisma.tradingAccount.findFirst({ where: { id: accountId, profileId } });
  if (!existing) return null;
  return prisma.tradingAccount.update({ where: { id: accountId }, data: input });
}

/** Delete a trading account. Trades keep existing (accountId set null). */
export async function deleteAccount(profileId: string, accountId: string): Promise<boolean> {
  const result = await prisma.tradingAccount.deleteMany({ where: { id: accountId, profileId } });
  return result.count > 0;
}

// ── Execution history (stop/target modifications, partial exits) ────────────

/** List the execution log for a trade (newest first). */
export async function listTradeExecutions(profileId: string, tradeId: string) {
  const trade = await prisma.trade.findFirst({ where: { id: tradeId, profileId }, select: { id: true } });
  if (!trade) return [];
  return prisma.tradeExecution.findMany({ where: { tradeId }, orderBy: { createdAt: "desc" } });
}

// ── Free-form journal entries (Phase 5) ──────────────────────────────────────

/** List free-form journal entries (newest first). */
export async function listJournalEntries(profileId: string) {
  return prisma.journalEntry.findMany({ where: { profileId }, orderBy: { createdAt: "desc" } });
}

export interface JournalEntryInput {
  title: string;
  body: string;
}

/** Create a free-form journal entry. */
export async function createJournalEntry(profileId: string, input: JournalEntryInput) {
  return prisma.journalEntry.create({
    data: { profileId, title: input.title, body: input.body },
  });
}

/** Update a free-form journal entry. */
export async function updateJournalEntry(profileId: string, entryId: string, input: Partial<JournalEntryInput>) {
  const existing = await prisma.journalEntry.findFirst({ where: { id: entryId, profileId } });
  if (!existing) return null;
  return prisma.journalEntry.update({ where: { id: entryId }, data: input });
}

/** Delete a free-form journal entry. */
export async function deleteJournalEntry(profileId: string, entryId: string): Promise<boolean> {
  const result = await prisma.journalEntry.deleteMany({ where: { id: entryId, profileId } });
  return result.count > 0;
}

// ── Watchlist / pre-trade ideas / pending orders ─────────────────────────────

/** List watchlist items (open intents first, newest first). */
export async function listWatchlist(profileId: string) {
  return prisma.watchlistItem.findMany({
    where: { profileId },
    orderBy: [{ status: "asc" }, { createdAt: "desc" }],
  });
}

export interface WatchlistInput {
  symbol: string;
  direction?: "LONG" | "SHORT";
  idea?: string | null;
  trigger?: number | null;
  stopLoss?: number | null;
  takeProfit?: number | null;
  note?: string | null;
}

/** Create a watchlist item. */
export async function createWatchlistItem(profileId: string, input: WatchlistInput) {
  return prisma.watchlistItem.create({
    data: {
      profileId,
      symbol: input.symbol.toUpperCase(),
      direction: input.direction ?? "LONG",
      idea: input.idea ?? null,
      trigger: input.trigger ?? null,
      stopLoss: input.stopLoss ?? null,
      takeProfit: input.takeProfit ?? null,
      note: input.note ?? null,
    },
  });
}

export interface UpdateWatchlistInput extends Partial<WatchlistInput> {
  status?: "watching" | "triggered" | "entered" | "expired";
}

/** Update a watchlist item. */
export async function updateWatchlistItem(profileId: string, id: string, input: UpdateWatchlistInput) {
  const existing = await prisma.watchlistItem.findFirst({ where: { id, profileId } });
  if (!existing) return null;
  return prisma.watchlistItem.update({
    where: { id },
    data: {
      ...(input.symbol !== undefined ? { symbol: input.symbol.toUpperCase() } : {}),
      ...(input.direction !== undefined ? { direction: input.direction } : {}),
      ...(input.idea !== undefined ? { idea: input.idea } : {}),
      ...(input.trigger !== undefined ? { trigger: input.trigger } : {}),
      ...(input.stopLoss !== undefined ? { stopLoss: input.stopLoss } : {}),
      ...(input.takeProfit !== undefined ? { takeProfit: input.takeProfit } : {}),
      ...(input.note !== undefined ? { note: input.note } : {}),
      ...(input.status !== undefined ? { status: input.status } : {}),
    },
  });
}

/** Delete a watchlist item. */
export async function deleteWatchlistItem(profileId: string, id: string): Promise<boolean> {
  const result = await prisma.watchlistItem.deleteMany({ where: { id, profileId } });
  return result.count > 0;
}

// ── Chart annotations (entry/stop/target/FVG/BOS/…) ──────────────────────────

/** List annotations for a trade. */
export async function listTradeAnnotations(profileId: string, tradeId: string) {
  const trade = await prisma.trade.findFirst({ where: { id: tradeId, profileId }, select: { id: true } });
  if (!trade) return [];
  return prisma.tradeAnnotation.findMany({ where: { tradeId }, orderBy: { createdAt: "asc" } });
}

export interface AnnotationInput {
  kind: string;
  label?: string | null;
  x?: number | null;
  y?: number | null;
}

/** Add a chart annotation to a trade. */
export async function addTradeAnnotation(profileId: string, tradeId: string, input: AnnotationInput) {
  const trade = await prisma.trade.findFirst({ where: { id: tradeId, profileId }, select: { id: true } });
  if (!trade) return null;
  return prisma.tradeAnnotation.create({
    data: {
      tradeId,
      kind: input.kind,
      label: input.label ?? null,
      x: input.x ?? null,
      y: input.y ?? null,
    },
  });
}

/** Delete a chart annotation. */
export async function deleteTradeAnnotation(profileId: string, annotationId: string): Promise<boolean> {
  const ann = await prisma.tradeAnnotation.findUnique({ where: { id: annotationId } });
  if (!ann) return false;
  const trade = await prisma.trade.findFirst({ where: { id: ann.tradeId, profileId }, select: { id: true } });
  if (!trade) return false;
  await prisma.tradeAnnotation.delete({ where: { id: annotationId } });
  return true;
}

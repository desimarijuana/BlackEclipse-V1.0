// ── Journal broker sync (server-only) ────────────────────────────────────────
// One-way projection: broker facts → journal trades.
//
// Guarantees:
//  • idempotent — a trade is keyed by (profileId, externalId), so re-running a
//    sync never duplicates it;
//  • non-destructive — only broker-owned fields are written. Notes, emotion,
//    confidence, grade, checklist, screenshots and a user's own strategy/setup
//    attribution are never overwritten;
//  • honest — a failed broker read writes no trades and records the reason;
//  • tombstoned — a broker trade the user deleted stays deleted (`ignoredAt`).

import { prisma, yieldToEventLoop } from "@/lib/db";
import { getOrCreateProfile } from "@/lib/journal/data";
import { BrokerSourceUnavailable, readBrokerMirror, syncBrokerMirror } from "./source";
import {
  projectBrokerTrades,
  type ProjectedFill,
  type ProjectedTrade,
} from "./project";
import {
  getBrokerLink,
  listAttributionRules,
  type BrokerLink,
} from "./links";

export interface BrokerSyncSummary {
  ok: boolean;
  connectionId: string;
  linkId: string | null;
  status: "ok" | "error" | "unavailable";
  imported: number;
  updated: number;
  unchanged: number;
  ignored: number;
  openPositions: number;
  totalProjected: number;
  skippedDeals: number;
  warnings: string[];
  /** Explicit broker window requested for this sync, or null for incremental. */
  backfillDays: number | null;
  error?: string;
  lastSyncedAt?: string | null;
}

export interface BrokerPreviewTrade {
  symbol: string;
  direction: "LONG" | "SHORT";
  entry: number;
  exit: number | null;
  quantity: number;
  netPnl: number;
  status: "open" | "closed";
  entryTime: string;
  exitTime: string | null;
}

export interface BrokerPreview {
  ok: boolean;
  connectionId: string;
  linkId: string | null;
  willImport: number;
  willUpdate: number;
  unchanged: number;
  ignored: number;
  openPositions: number;
  totalProjected: number;
  skippedDeals: number;
  warnings: string[];
  sample: BrokerPreviewTrade[];
  error?: string;
}

interface Derived {
  grossPnl: number;
  commission: number;
  fee: number;
  pnl: number;
  pnlPct: number;
  rMultiple: number;
  riskAmount: number | null;
  rewardAmount: number | null;
  actualRR: number | null;
  durationSec: number | null;
}

function derive(trade: ProjectedTrade): Derived {
  const sign = trade.direction === "LONG" ? 1 : -1;
  const riskPerUnit = trade.stopLoss != null ? (trade.entry - trade.stopLoss) * sign : null;
  const rewardPerUnit = trade.takeProfit != null ? (trade.takeProfit - trade.entry) * sign : null;
  const riskAmount =
    riskPerUnit != null && riskPerUnit > 0 ? riskPerUnit * trade.quantity : null;
  const rewardAmount =
    rewardPerUnit != null && rewardPerUnit > 0 ? rewardPerUnit * trade.quantity : null;

  const isOpen = trade.status === "open";
  const entryMs = Date.parse(trade.entryTime);
  const exitMs = trade.exitTime ? Date.parse(trade.exitTime) : NaN;
  const durationSec =
    !isOpen && Number.isFinite(entryMs) && Number.isFinite(exitMs)
      ? Math.max(0, Math.round((exitMs - entryMs) / 1000))
      : null;

  return {
    grossPnl: trade.grossPnl,
    commission: trade.commission,
    fee: trade.fee,
    pnl: trade.netPnl,
    // Account-currency P&L over notional is a rough ratio (FX/CFD contract
    // size is not modelled); `pnl` and `rMultiple` remain the authoritative
    // numbers. Never let a division by zero fabricate a percentage.
    pnlPct: trade.entry > 0 && trade.quantity > 0 ? trade.netPnl / (trade.entry * trade.quantity) : 0,
    rMultiple: riskAmount ? trade.netPnl / riskAmount : 0,
    riskAmount,
    rewardAmount,
    actualRR:
      riskPerUnit != null && rewardPerUnit != null && riskPerUnit > 0
        ? rewardPerUnit / riskPerUnit
        : null,
    durationSec,
  };
}

function dayDateFor(trade: ProjectedTrade): Date {
  const stamp = trade.status === "open" ? trade.entryTime : trade.exitTime ?? trade.entryTime;
  return new Date(`${stamp.slice(0, 10)}T00:00:00Z`);
}

function sameNumber(a: number | null | undefined, b: number | null | undefined): boolean {
  const av = a ?? null;
  const bv = b ?? null;
  if (av == null && bv == null) return true;
  if (av == null || bv == null) return false;
  return Math.abs(av - bv) < 1e-9;
}

function sameTime(a: Date | null, iso: string | null): boolean {
  if (a == null && iso == null) return true;
  if (a == null || iso == null) return false;
  return a.getTime() === Date.parse(iso);
}

interface SyncOptions {
  /** Re-read the broker mirror before projecting. Preview never syncs. */
  refresh?: boolean;
  /** Force the link's full backfill window instead of the computed gap. */
  fullBackfill?: boolean;
}

async function contextFor(profileId: string, connectionId: string) {
  const [link, rules, strategies, setups] = await Promise.all([
    getBrokerLink(profileId, connectionId),
    listAttributionRules(profileId),
    prisma.strategy.findMany({ where: { profileId }, select: { id: true } }),
    prisma.setup.findMany({ where: { profileId }, select: { id: true } }),
  ]);
  const validStrategyIds = new Set(strategies.map((s) => s.id));
  const validSetupIds = new Set(setups.map((s) => s.id));
  // A rule with no connectionId applies to every connection; otherwise it is
  // scoped to the connection being projected.
  const applicable = rules.filter(
    (rule) => !rule.connectionId || rule.connectionId === connectionId,
  );
  return { link, rules: applicable, validStrategyIds, validSetupIds };
}

function sanitizeProjection(
  trade: ProjectedTrade,
  validStrategyIds: Set<string>,
  validSetupIds: Set<string>,
): ProjectedTrade {
  return {
    ...trade,
    strategyId: trade.strategyId && validStrategyIds.has(trade.strategyId) ? trade.strategyId : null,
    setupId: trade.setupId && validSetupIds.has(trade.setupId) ? trade.setupId : null,
  };
}

/**
 * Two servers (dev + prod) can share the same SQLite files, so the in-process
 * sync lock is not the only writer. A unique-constraint race means the other
 * process already inserted the row; that is success, not an error.
 */
function isUniqueViolation(err: unknown): boolean {
  return (
    typeof err === "object" &&
    err != null &&
    ((err as { code?: string }).code === "P2002" ||
      /unique constraint/i.test(String((err as { message?: string }).message ?? "")))
  );
}

/**
 * Insert any deal the journal has not stored yet. Deals are immutable, so an
 * existing ticket is never rewritten; a repeated sync is a no-op.
 */
async function syncFills(tradeId: string, fills: ProjectedFill[]): Promise<void> {
  if (!fills.length) return;
  const existing = await prisma.tradeFill.findMany({
    where: { tradeId },
    select: { dealTicket: true },
  });
  const have = new Set(existing.map((row) => row.dealTicket));
  const missing = fills.filter((fill) => !have.has(fill.dealTicket));
  if (!missing.length) return;
  try {
    await prisma.tradeFill.createMany({
      data: missing.map((fill) => ({
        tradeId,
        dealTicket: fill.dealTicket,
        orderTicket: fill.orderTicket,
        positionTicket: fill.positionTicket,
        side: fill.side,
        entry: fill.entry,
        volume: fill.volume,
        price: fill.price,
        commission: fill.commission,
        swap: fill.swap,
        profit: fill.profit,
        magic: fill.magic,
        comment: fill.comment,
        dealtAt: new Date(fill.dealtAt),
      })),
    });
  } catch (err) {
    if (!isUniqueViolation(err)) throw err;
    // Another process projected the same deals first.
  }
}

async function markLink(
  link: BrokerLink | null,
  data: { status: string; error?: string | null; lastDealAt?: number | null; synced?: boolean },
): Promise<void> {
  if (!link) return;
  await prisma.journalBrokerLink.update({
    where: { id: link.id },
    data: {
      lastSyncStatus: data.status,
      lastError: data.error ?? null,
      ...(data.lastDealAt != null ? { lastDealAt: data.lastDealAt } : {}),
      ...(data.synced ? { lastSyncedAt: new Date() } : {}),
    },
  });
}

function emptySummary(
  connectionId: string,
  linkId: string | null,
  status: BrokerSyncSummary["status"],
  error?: string,
): BrokerSyncSummary {
  return {
    ok: false,
    connectionId,
    linkId,
    status,
    imported: 0,
    updated: 0,
    unchanged: 0,
    ignored: 0,
    openPositions: 0,
    totalProjected: 0,
    skippedDeals: 0,
    warnings: [],
    backfillDays: null,
    error,
  };
}

/**
 * How wide a broker window this sync needs.
 *
 * The reconciler's ordinary pass reads a small rolling window. That is enough
 * to keep a recently-synced mirror current, but it cannot recover the gap after
 * the app (or the link) was idle for a while. Hook `lastSyncedAt` gives the
 * honest gap; below ~5 days the rolling window already covers it.
 */
function historyWindowDays(link: BrokerLink): number | undefined {
  if (!link.lastSyncedAt) return link.backfillDays;
  const last = Date.parse(link.lastSyncedAt);
  if (!Number.isFinite(last)) return link.backfillDays;
  const gapDays = Math.ceil((Date.now() - last) / 86_400_000);
  if (gapDays <= 5) return undefined;
  return Math.min(link.backfillDays, Math.max(7, gapDays + 2));
}

/**
 * Read the broker mirror and compare it with the journal without writing.
 * This is what the first-connect UI shows before anything is committed.
 */
export async function previewJournalBroker(
  profileId: string,
  connectionId: string,
): Promise<BrokerPreview> {
  const { link, rules, validStrategyIds, validSetupIds } = await contextFor(profileId, connectionId);
  try {
    const mirror = await readBrokerMirror(connectionId);
    const result = projectBrokerTrades(mirror.deals, mirror.positions, {
      connectionId,
      symbolMap: link?.symbolMap,
      rules,
    });
    const projected = result.trades.map((trade) =>
      sanitizeProjection(trade, validStrategyIds, validSetupIds),
    );

    const existing = await prisma.trade.findMany({
      where: { profileId, brokerConnectionId: connectionId, externalId: { not: null } },
      select: { externalId: true, ignoredAt: true },
    });
    const existingIds = new Map(existing.map((row) => [row.externalId as string, row.ignoredAt]));

    let willImport = 0;
    let willUpdate = 0;
    let ignored = 0;
    for (const trade of projected) {
      if (existingIds.has(trade.externalId)) {
        if (existingIds.get(trade.externalId)) ignored += 1;
        else willUpdate += 1;
      } else {
        willImport += 1;
      }
    }

    return {
      ok: true,
      connectionId,
      linkId: link?.id ?? null,
      willImport,
      willUpdate,
      // "unchanged" cannot be proven without reading every field; preview
      // reports candidates conservatively and sync reports the real count.
      unchanged: 0,
      ignored,
      openPositions: projected.filter((t) => t.status === "open").length,
      totalProjected: projected.length,
      skippedDeals: result.skippedDeals,
      warnings: result.warnings,
      sample: projected.slice(0, 10).map((t) => ({
        symbol: t.symbol,
        direction: t.direction,
        entry: t.entry,
        exit: t.exit,
        quantity: t.quantity,
        netPnl: t.netPnl,
        status: t.status,
        entryTime: t.entryTime,
        exitTime: t.exitTime,
      })),
    };
  } catch (err) {
    return {
      ok: false,
      connectionId,
      linkId: link?.id ?? null,
      willImport: 0,
      willUpdate: 0,
      unchanged: 0,
      ignored: 0,
      openPositions: 0,
      totalProjected: 0,
      skippedDeals: 0,
      warnings: [],
      sample: [],
      error: err instanceof Error ? err.message : "broker preview failed",
    };
  }
}

/**
 * Refresh the broker mirror, project it, and upsert journal trades.
 *
 * A manual sync, another browser tab and the auto-sync timer can all ask at
 * once. The per-connection promise lock coalesces them onto one run, so two
 * writers never race the unique `externalId`/`dealTicket` keys or hammer the
 * terminal. A caller asking for a full backfill while an incremental sync is
 * already running receives that run, not a second one.
 */
const inflight = ((
  globalThis as unknown as { __journalBrokerInflight?: Map<string, Promise<BrokerSyncSummary>> }
).__journalBrokerInflight ??= new Map<string, Promise<BrokerSyncSummary>>());

export async function syncJournalBroker(
  profileId: string,
  connectionId: string,
  options: SyncOptions = {},
): Promise<BrokerSyncSummary> {
  const key = `${profileId}:${connectionId}`;
  const running = inflight.get(key);
  if (running) return running;
  const run = runJournalBrokerSync(profileId, connectionId, options).finally(() => {
    inflight.delete(key);
  });
  inflight.set(key, run);
  return run;
}

async function runJournalBrokerSync(
  profileId: string,
  connectionId: string,
  options: SyncOptions = {},
): Promise<BrokerSyncSummary> {
  const { link, rules, validStrategyIds, validSetupIds } = await contextFor(profileId, connectionId);

  if (!link) {
    return emptySummary(connectionId, null, "error", "No journal link for this broker connection");
  }
  if (!link.enabled) {
    return emptySummary(connectionId, link.id, "error", "This journal link is disabled");
  }

  const windowDays = options.fullBackfill ? link.backfillDays : historyWindowDays(link);

  if (options.refresh !== false) {
    try {
      const result = await syncBrokerMirror(
        connectionId,
        windowDays != null ? { days: windowDays } : {},
      );
      if (!result.ok) {
        const reason =
          typeof result.error === "string"
            ? result.error
            : (result.error as { reason?: string; message?: string } | undefined)?.reason ??
              (result.error as { message?: string } | undefined)?.message ??
              "broker sync failed";
        await markLink(link, { status: "unavailable", error: reason });
        return emptySummary(connectionId, link.id, "unavailable", reason);
      }
    } catch (err) {
      const code = err instanceof BrokerSourceUnavailable ? err.code : "REQUEST_FAILED";
      const status = code === "REQUEST_FAILED" ? "error" : "unavailable";
      await markLink(link, { status, error: err instanceof Error ? err.message : "broker sync failed" });
      return emptySummary(
        connectionId,
        link.id,
        status,
        err instanceof Error ? err.message : "broker sync failed",
      );
    }
  }

  let projected: ProjectedTrade[];
  let warnings: string[];
  let skippedDeals: number;
  let lastDealAt: number | null = null;
  try {
    const mirror = await readBrokerMirror(connectionId);
    const result = projectBrokerTrades(mirror.deals, mirror.positions, {
      connectionId,
      symbolMap: link.symbolMap,
      rules,
    });
    projected = result.trades.map((trade) => sanitizeProjection(trade, validStrategyIds, validSetupIds));
    warnings = result.warnings;
    skippedDeals = result.skippedDeals;
    lastDealAt = mirror.deals.reduce((max, deal) => Math.max(max, deal.dealtAt || 0), 0) || null;
  } catch (err) {
    const code = err instanceof BrokerSourceUnavailable ? err.code : "REQUEST_FAILED";
    const status = code === "REQUEST_FAILED" ? "error" : "unavailable";
    await markLink(link, { status, error: err instanceof Error ? err.message : "broker read failed" });
    return emptySummary(
      connectionId,
      link.id,
      status,
      err instanceof Error ? err.message : "broker read failed",
    );
  }

  const existingRows = await prisma.trade.findMany({
    where: { profileId, brokerConnectionId: connectionId, externalId: { not: null } },
    include: {
      tags: { include: { tag: { select: { name: true } } } },
      _count: { select: { fills: true } },
    },
  });
  const existing = new Map(existingRows.map((row) => [row.externalId as string, row]));

  let imported = 0;
  let updated = 0;
  let unchanged = 0;
  let ignored = 0;

  for (let i = 0; i < projected.length; i++) {
    const trade = projected[i];
    const current = existing.get(trade.externalId);

    if (current?.ignoredAt) {
      ignored += 1;
      continue;
    }

    const derived = derive(trade);
    const day = await prisma.journalDay.upsert({
      where: { profileId_date: { profileId, date: dayDateFor(trade) } },
      update: {},
      create: { profileId, date: dayDateFor(trade) },
    });

    if (!current) {
      const tagNames = [...new Set(trade.tagNames ?? [])].filter(Boolean);
      let created: { id: string };
      try {
        created = await prisma.trade.create({
        data: {
          profileId,
          accountId: link.accountId,
          dayId: day.id,
          strategyId: trade.strategyId,
          setupId: trade.setupId,
          symbol: trade.symbol.toUpperCase(),
          direction: trade.direction,
          entry: trade.entry,
          exit: trade.exit,
          stopLoss: trade.stopLoss,
          takeProfit: trade.takeProfit,
          quantity: trade.quantity,
          entryTime: new Date(trade.entryTime),
          exitTime: trade.exitTime ? new Date(trade.exitTime) : null,
          status: trade.status,
          source: "broker",
          externalId: trade.externalId,
          brokerConnectionId: connectionId,
          brokerPositionTicket: trade.brokerPositionTicket,
          magic: trade.magic ?? null,
          pnlBasis: trade.pnlBasis,
          grossPnl: derived.grossPnl,
          commission: derived.commission,
          fee: derived.fee,
          pnl: derived.pnl,
          pnlPct: derived.pnlPct,
          rMultiple: derived.rMultiple,
          riskAmount: derived.riskAmount,
          rewardAmount: derived.rewardAmount,
          actualRR: derived.actualRR,
          durationSec: derived.durationSec,
          executions: {
            create: {
              kind: "created",
              detail: JSON.stringify({
                source: "broker",
                externalId: trade.externalId,
                fillCount: trade.fillCount,
              }),
            },
          },
          tags: tagNames.length
            ? {
                create: tagNames.map((name) => ({
                  tag: {
                    connectOrCreate: {
                      where: { profileId_name: { profileId, name } },
                      create: { profileId, name },
                    },
                  },
                })),
              }
            : undefined,
        },
        });
      } catch (err) {
        if (isUniqueViolation(err)) {
          // The other process won the insert. Its row will converge on the next
          // sync; do not fail the whole import.
          const raced = await prisma.trade.findFirst({
            where: { profileId, externalId: trade.externalId },
            select: { id: true },
          });
          if (raced) {
            await syncFills(raced.id, trade.fills);
            continue;
          }
        }
        throw err;
      }
      await syncFills(created.id, trade.fills);
      imported += 1;
      continue;
    }

    // Broker owns execution fields; the user owns everything else.
    // A user's own strategy/setup attribution is never replaced.
    const desiredStrategyId = current.strategyId ?? trade.strategyId;
    const desiredSetupId = current.setupId ?? trade.setupId;
    const desiredAccountId = link.accountId ?? current.accountId;
    // MT5 history deals do not carry the position's SL/TP. A snapshot captured
    // while the position was open is the only source; never erase it on close.
    const desiredStopLoss = trade.stopLoss ?? current.stopLoss;
    const desiredTakeProfit = trade.takeProfit ?? current.takeProfit;
    const updateDerived = derive({
      ...trade,
      stopLoss: desiredStopLoss,
      takeProfit: desiredTakeProfit,
    });

    const changed =
      current.symbol !== trade.symbol.toUpperCase() ||
      current.direction !== trade.direction ||
      !sameNumber(current.entry, trade.entry) ||
      !sameNumber(current.exit, trade.exit) ||
      !sameNumber(current.stopLoss, desiredStopLoss) ||
      !sameNumber(current.takeProfit, desiredTakeProfit) ||
      !sameNumber(current.quantity, trade.quantity) ||
      !sameTime(current.entryTime, trade.entryTime) ||
      !sameTime(current.exitTime, trade.exitTime) ||
      current.status !== trade.status ||
      current.magic !== (trade.magic ?? null) ||
      !sameNumber(current.pnl, updateDerived.pnl) ||
      !sameNumber(current.commission, updateDerived.commission) ||
      !sameNumber(current.fee, updateDerived.fee) ||
      !sameNumber(current.grossPnl, updateDerived.grossPnl) ||
      !sameNumber(current.rMultiple, updateDerived.rMultiple) ||
      !sameNumber(current.riskAmount, updateDerived.riskAmount) ||
      !sameNumber(current.rewardAmount, updateDerived.rewardAmount) ||
      !sameNumber(current.actualRR, updateDerived.actualRR) ||
      current.durationSec !== updateDerived.durationSec ||
      current.dayId !== day.id ||
      current.accountId !== desiredAccountId ||
      current.strategyId !== desiredStrategyId ||
      current.setupId !== desiredSetupId ||
      current.pnlBasis !== trade.pnlBasis;

    const currentTags = new Set(current.tags.map((t) => t.tag.name));
    const missingTags = [...new Set(trade.tagNames ?? [])].filter(
      (name) => name && !currentTags.has(name),
    );

    if (!changed && missingTags.length === 0) {
      // Fills are independent of the aggregate fields; a trade that needed no
      // update can still be missing deals (e.g. right after this phase ships).
      if (current._count.fills < trade.fills.length) {
        await syncFills(current.id, trade.fills);
      }
      unchanged += 1;
      continue;
    }

    await prisma.trade.update({
      where: { id: current.id },
      data: {
        accountId: desiredAccountId,
        dayId: day.id,
        strategyId: desiredStrategyId,
        setupId: desiredSetupId,
        symbol: trade.symbol.toUpperCase(),
        direction: trade.direction,
        entry: trade.entry,
        exit: trade.exit,
        stopLoss: desiredStopLoss,
        takeProfit: desiredTakeProfit,
        quantity: trade.quantity,
        entryTime: new Date(trade.entryTime),
        exitTime: trade.exitTime ? new Date(trade.exitTime) : null,
        status: trade.status,
        magic: trade.magic ?? null,
        pnlBasis: trade.pnlBasis,
        grossPnl: updateDerived.grossPnl,
        commission: updateDerived.commission,
        fee: updateDerived.fee,
        pnl: updateDerived.pnl,
        pnlPct: updateDerived.pnlPct,
        rMultiple: updateDerived.rMultiple,
        riskAmount: updateDerived.riskAmount,
        rewardAmount: updateDerived.rewardAmount,
        actualRR: updateDerived.actualRR,
        durationSec: updateDerived.durationSec,
        ...(changed
          ? {
              executions: {
                create: {
                  kind: "broker_reconciled",
                  detail: JSON.stringify({
                    externalId: trade.externalId,
                    previous: {
                      entry: current.entry,
                      exit: current.exit,
                      quantity: current.quantity,
                      status: current.status,
                      pnl: current.pnl,
                    },
                    next: {
                      entry: trade.entry,
                      exit: trade.exit,
                      quantity: trade.quantity,
                      status: trade.status,
                      pnl: updateDerived.pnl,
                    },
                  }),
                },
              },
            }
          : {}),
        ...(missingTags.length
          ? {
              tags: {
                create: missingTags.map((name) => ({
                  tag: {
                    connectOrCreate: {
                      where: { profileId_name: { profileId, name } },
                      create: { profileId, name },
                    },
                  },
                })),
              },
            }
          : {}),
      },
    });
    await syncFills(current.id, trade.fills);
    updated += 1;

    // A batch of broker writes must not starve the event loop.
    if (i > 0 && i % 25 === 0) await yieldToEventLoop();
  }

  await markLink(link, {
    status: "ok",
    error: warnings.length ? warnings.slice(0, 3).join("; ") : null,
    lastDealAt,
    synced: true,
  });

  return {
    ok: true,
    connectionId,
    linkId: link.id,
    status: "ok",
    imported,
    updated,
    unchanged,
    ignored,
    openPositions: projected.filter((t) => t.status === "open").length,
    totalProjected: projected.length,
    skippedDeals,
    warnings,
    backfillDays: windowDays ?? null,
    lastSyncedAt: new Date().toISOString(),
  };
}

/** Convenience for the route: resolve the guest profile once. */
export async function syncDefaultProfile(connectionId: string): Promise<BrokerSyncSummary> {
  const profileId = await getOrCreateProfile();
  return syncJournalBroker(profileId, connectionId);
}


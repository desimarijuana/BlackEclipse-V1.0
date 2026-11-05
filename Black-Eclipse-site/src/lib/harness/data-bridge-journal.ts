// Journal → runtime bridge. READ-ONLY by construction: there is no write path
// in this module. The Python trade-learning nodes request a bounded window of
// the journal; the server resolves the owner and never trusts a client-supplied
// profile id.
//
// Split out of `data-bridge.ts` (which is at its size ratchet) and dispatched
// from `data-bridge-extensions.ts`.

import { prisma } from "@/lib/db";
import { unavailable } from "@/lib/harness/data-bridge-result";
import type { DataBridgeResult } from "@/lib/harness/data-bridge-types";

const MAX_TRADES = 500;
const MAX_SYMBOLS = 50;
const MAX_EXECUTIONS_PER_TRADE = 20;

function text(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function list(value: unknown): string[] {
  if (Array.isArray(value)) return value.map((item) => String(item).trim()).filter(Boolean);
  if (typeof value === "string") {
    return value.split(",").map((item) => item.trim()).filter(Boolean);
  }
  return [];
}

function jsonValue<T>(raw: string | null, fallback: T): T {
  if (!raw) return fallback;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

/**
 * Resolve the journal profile for a trusted runtime call.
 *
 * The Python runtime is the only caller of this capability (authenticated or
 * loopback). It passes the run's `userId`; the server maps that to the SAME
 * profile the journal UI would use. When auth is off or the id is unknown, the
 * guest profile is the only fallback — never another user's profile.
 */
async function resolveProfile(userId: string) {
  if (userId) {
    const owned = await prisma.journalProfile.findFirst({
      where: { userId },
      select: { id: true, userId: true },
    });
    if (owned) return owned;
  }
  return prisma.journalProfile.findFirst({
    where: { userId: null },
    orderBy: { createdAt: "asc" },
    select: { id: true, userId: true },
  });
}

export async function journalTradesCapability(
  params: Record<string, unknown>,
): Promise<DataBridgeResult> {
  const userId = text(params.userId);
  const profile = await resolveProfile(userId);
  if (!profile) {
    // No journal exists yet. That is a real answer, not an empty trade list that
    // would read as "you made no mistakes".
    return unavailable("no journal profile exists yet");
  }

  const lookbackDays = Math.max(1, Math.min(Number(params.lookbackDays) || 90, 3650));
  const limit = Math.max(1, Math.min(Number(params.limit) || 200, MAX_TRADES));
  const statusRaw = text(params.status).toLowerCase();
  const status = statusRaw === "open" ? "open" : statusRaw === "all" ? "" : "closed";
  const symbols = list(params.symbols).slice(0, MAX_SYMBOLS).map((s) => s.toUpperCase());
  const strategyId = text(params.strategyId);
  const setupId = text(params.setupId);
  const includeExecutions = params.includeExecutions !== false;
  const cutoff = new Date(Date.now() - lookbackDays * 86_400_000);

  const rows = await prisma.trade.findMany({
    where: {
      profileId: profile.id,
      ignoredAt: null,
      ...(status ? { status } : {}),
      entryTime: { gte: cutoff },
      ...(symbols.length ? { symbol: { in: symbols } } : {}),
      ...(strategyId ? { strategyId } : {}),
      ...(setupId ? { setupId } : {}),
    },
    include: {
      strategy: {
        select: {
          name: true,
          rules: { select: { id: true, text: true, category: true } },
        },
      },
      setup: { select: { name: true } },
    },
    orderBy: { entryTime: "asc" },
    take: limit,
  });

  const ids = rows.map((row) => row.id);
  const executionRows = includeExecutions && ids.length > 0
    ? await prisma.tradeExecution.findMany({
        where: { tradeId: { in: ids } },
        orderBy: { createdAt: "asc" },
        select: { tradeId: true, kind: true, detail: true, createdAt: true },
      })
    : [];

  const executions: Record<string, Array<{ kind: string; detail: unknown; createdAt: string }>> = {};
  for (const row of executionRows) {
    const bucket = (executions[row.tradeId] ??= []);
    if (bucket.length >= MAX_EXECUTIONS_PER_TRADE) continue;
    bucket.push({
      kind: row.kind,
      detail: jsonValue<unknown>(row.detail, null),
      createdAt: row.createdAt.toISOString(),
    });
  }

  const trades = rows.map((row) => ({
    id: row.id,
    symbol: row.symbol,
    direction: row.direction,
    entry: row.entry,
    exit: row.exit,
    stopLoss: row.stopLoss,
    takeProfit: row.takeProfit,
    quantity: row.quantity,
    entryTime: row.entryTime.toISOString(),
    exitTime: row.exitTime ? row.exitTime.toISOString() : null,
    status: row.status,
    session: row.session,
    strategyId: row.strategyId,
    strategyName: row.strategy?.name ?? null,
    setupId: row.setupId,
    setupName: row.setup?.name ?? null,
    emotion: row.emotion,
    confidence: row.confidence,
    checklist: jsonValue<Record<string, boolean>>(row.checklist, {}),
    grade: row.grade,
    notes: row.notes,
    mistakes: jsonValue<string[]>(row.mistakes, []),
    riskAmount: row.riskAmount,
    rMultiple: row.rMultiple,
    mfe: row.mfe,
    mae: row.mae,
    pnl: row.pnl,
    pnlPct: row.pnlPct,
    durationSec: row.durationSec,
    actualRR: row.actualRR,
    strategyRules: row.strategy?.rules?.map((rule) => ({
      id: rule.id,
      text: rule.text,
      category: rule.category,
    })) ?? [],
  }));

  const closed = trades.filter((trade) => trade.status === "closed");
  const denominator = Math.max(trades.length, 1);
  return {
    status: "OK",
    value: {
      trades,
      executions,
      completeness: {
        trades: trades.length,
        closed: closed.length,
        withStop: trades.filter((trade) => trade.stopLoss !== null).length,
        withRisk: trades.filter((trade) => trade.riskAmount !== null).length,
        withMfeMae: trades.filter((trade) => trade.mfe !== null && trade.mae !== null).length,
        withPlan: trades.filter((trade) => trade.strategyId || trade.setupId).length,
        reviewed: trades.filter((trade) => trade.grade || trade.notes).length,
        fractionWithRisk: Math.round(
          (trades.filter((t) => t.riskAmount !== null).length / denominator) * 10_000,
        ) / 10_000,
      },
      truncated: rows.length === limit,
      provenance: {
        source: "jdds",
        readAt: new Date().toISOString(),
        profileId: profile.id,
        lookbackDays,
        status: status || "all",
      },
    },
  };
}

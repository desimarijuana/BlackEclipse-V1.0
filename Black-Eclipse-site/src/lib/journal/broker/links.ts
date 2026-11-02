// ── Journal ↔ broker links (server-only) ─────────────────────────────────────
// A link says "project this broker connection into this journal account".
// The broker connection itself (and its credentials) lives in the Python
// harness; nothing here stores a secret.

import { prisma } from "@/lib/db";
import type { AttributionRule } from "./project";

export interface BrokerLink {
  id: string;
  profileId: string;
  connectionId: string;
  accountId: string | null;
  enabled: boolean;
  autoSync: boolean;
  backfillDays: number;
  lastDealAt: number | null;
  lastSyncedAt: string | null;
  lastSyncStatus: string;
  lastError: string | null;
  symbolMap: Record<string, string>;
  createdAt: string;
  updatedAt: string;
}

export interface BrokerLinkInput {
  connectionId: string;
  accountId?: string | null;
  enabled?: boolean;
  autoSync?: boolean;
  backfillDays?: number;
  symbolMap?: Record<string, string> | null;
}

export interface BrokerLinkPatch {
  accountId?: string | null;
  enabled?: boolean;
  autoSync?: boolean;
  backfillDays?: number;
  symbolMap?: Record<string, string> | null;
}

const MIN_BACKFILL_DAYS = 7;
const MAX_BACKFILL_DAYS = 3650;

function parseSymbolMap(raw: string | null): Record<string, string> {
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    const out: Record<string, string> = {};
    for (const [key, value] of Object.entries(parsed as Record<string, unknown>)) {
      const k = key.trim();
      const v = typeof value === "string" ? value.trim() : "";
      if (k && v) out[k] = v;
    }
    return out;
  } catch {
    return {};
  }
}

function serializeSymbolMap(map?: Record<string, string> | null): string | null {
  if (!map) return null;
  const clean: Record<string, string> = {};
  for (const [key, value] of Object.entries(map)) {
    const k = key.trim();
    const v = String(value ?? "").trim();
    if (k && v) clean[k] = v;
  }
  return Object.keys(clean).length ? JSON.stringify(clean) : null;
}

function clampBackfill(days: number | undefined, fallback = 90): number {
  const value = Number(days ?? fallback);
  if (!Number.isFinite(value)) return fallback;
  return Math.min(MAX_BACKFILL_DAYS, Math.max(MIN_BACKFILL_DAYS, Math.round(value)));
}

function toLink(row: {
  id: string;
  profileId: string;
  connectionId: string;
  accountId: string | null;
  enabled: boolean;
  autoSync: boolean;
  backfillDays: number;
  lastDealAt: number | null;
  lastSyncedAt: Date | null;
  lastSyncStatus: string;
  lastError: string | null;
  symbolMap: string | null;
  createdAt: Date;
  updatedAt: Date;
}): BrokerLink {
  return {
    id: row.id,
    profileId: row.profileId,
    connectionId: row.connectionId,
    accountId: row.accountId,
    enabled: row.enabled,
    autoSync: row.autoSync,
    backfillDays: row.backfillDays,
    lastDealAt: row.lastDealAt,
    lastSyncedAt: row.lastSyncedAt ? row.lastSyncedAt.toISOString() : null,
    lastSyncStatus: row.lastSyncStatus,
    lastError: row.lastError,
    symbolMap: parseSymbolMap(row.symbolMap),
    createdAt: row.createdAt.toISOString(),
    updatedAt: row.updatedAt.toISOString(),
  };
}

export async function listBrokerLinks(profileId: string): Promise<BrokerLink[]> {
  const rows = await prisma.journalBrokerLink.findMany({
    where: { profileId },
    orderBy: { createdAt: "asc" },
  });
  return rows.map(toLink);
}

export async function getBrokerLink(profileId: string, connectionId: string): Promise<BrokerLink | null> {
  const row = await prisma.journalBrokerLink.findUnique({
    where: { profileId_connectionId: { profileId, connectionId } },
  });
  return row ? toLink(row) : null;
}

async function assertAccount(profileId: string, accountId: string | null | undefined): Promise<void> {
  if (!accountId) return;
  const account = await prisma.tradingAccount.findFirst({
    where: { id: accountId, profileId },
    select: { id: true },
  });
  if (!account) throw new Error("Trading account not found for this profile");
}

export async function createBrokerLink(profileId: string, input: BrokerLinkInput): Promise<BrokerLink> {
  const connectionId = String(input.connectionId ?? "").trim();
  if (!connectionId) throw new Error("connectionId is required");
  await assertAccount(profileId, input.accountId);
  const row = await prisma.journalBrokerLink.upsert({
    where: { profileId_connectionId: { profileId, connectionId } },
    update: {
      accountId: input.accountId ?? null,
      enabled: input.enabled ?? true,
      autoSync: input.autoSync ?? false,
      backfillDays: clampBackfill(input.backfillDays),
      symbolMap: serializeSymbolMap(input.symbolMap),
    },
    create: {
      profileId,
      connectionId,
      accountId: input.accountId ?? null,
      enabled: input.enabled ?? true,
      autoSync: input.autoSync ?? false,
      backfillDays: clampBackfill(input.backfillDays),
      symbolMap: serializeSymbolMap(input.symbolMap),
    },
  });
  return toLink(row);
}

export async function updateBrokerLink(
  profileId: string,
  linkId: string,
  patch: BrokerLinkPatch,
): Promise<BrokerLink | null> {
  const existing = await prisma.journalBrokerLink.findFirst({ where: { id: linkId, profileId } });
  if (!existing) return null;
  if (patch.accountId !== undefined) await assertAccount(profileId, patch.accountId);
  const row = await prisma.journalBrokerLink.update({
    where: { id: linkId },
    data: {
      ...(patch.accountId !== undefined ? { accountId: patch.accountId } : {}),
      ...(patch.enabled !== undefined ? { enabled: patch.enabled } : {}),
      ...(patch.autoSync !== undefined ? { autoSync: patch.autoSync } : {}),
      ...(patch.backfillDays !== undefined ? { backfillDays: clampBackfill(patch.backfillDays) } : {}),
      ...(patch.symbolMap !== undefined ? { symbolMap: serializeSymbolMap(patch.symbolMap) } : {}),
    },
  });
  return toLink(row);
}

export async function deleteBrokerLink(profileId: string, linkId: string): Promise<boolean> {
  const result = await prisma.journalBrokerLink.deleteMany({ where: { id: linkId, profileId } });
  return result.count > 0;
}

// ── Attribution rules ────────────────────────────────────────────────────────

export interface AttributionRuleInput {
  connectionId?: string | null;
  magic?: number | null;
  commentMatch?: string | null;
  symbolMatch?: string | null;
  strategyId?: string | null;
  setupId?: string | null;
  tagNames?: string[] | null;
  priority?: number;
}

function parseTags(raw: string | null): string[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return [];
  }
}

export async function listAttributionRules(profileId: string): Promise<AttributionRule[]> {
  const rows = await prisma.brokerAttributionRule.findMany({
    where: { profileId },
    orderBy: [{ priority: "desc" }, { createdAt: "asc" }],
  });
  return rows.map((row) => ({
    id: row.id,
    connectionId: row.connectionId,
    magic: row.magic,
    commentMatch: row.commentMatch,
    symbolMatch: row.symbolMatch,
    strategyId: row.strategyId,
    setupId: row.setupId,
    tagNames: parseTags(row.tagNames),
    priority: row.priority,
  }));
}

export async function createAttributionRule(
  profileId: string,
  input: AttributionRuleInput,
) {
  return prisma.brokerAttributionRule.create({
    data: {
      profileId,
      connectionId: input.connectionId?.trim() || null,
      magic: input.magic != null ? Math.trunc(Number(input.magic)) : null,
      commentMatch: input.commentMatch?.trim() || null,
      symbolMatch: input.symbolMatch?.trim() || null,
      strategyId: input.strategyId || null,
      setupId: input.setupId || null,
      tagNames: input.tagNames?.length ? JSON.stringify(input.tagNames) : null,
      priority: Number.isFinite(Number(input.priority)) ? Number(input.priority) : 0,
    },
  });
}

export async function deleteAttributionRule(profileId: string, ruleId: string): Promise<boolean> {
  const result = await prisma.brokerAttributionRule.deleteMany({
    where: { id: ruleId, profileId },
  });
  return result.count > 0;
}

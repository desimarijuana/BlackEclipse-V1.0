// ── Workflow schedules — persistence + the due-work query ────────────────────
// Server-only. A schedule stores a cron expression + IANA timezone and a
// PRECOMPUTED `nextRunAt`, so the tick is one indexed query. The last outcome is
// kept so a failing schedule is visible instead of silently retrying.
//
// Missed-fire policy: when the app was closed across fire times, the tick sees
// `nextRunAt` in the past. `catchUp: 'coalesce'` runs once now; `'skip'` just
// advances to the next future occurrence. Either way it never runs N times to
// "catch up" — a schedule must not storm on boot.

import { prisma } from '@/lib/db';
import { isValidCron, nextRunAt, parseCron } from './cron';

export interface ScheduleRecord {
  id: string;
  workflowId: string;
  name: string;
  cron: string;
  timezone: string;
  enabled: boolean;
  catchUp: 'skip' | 'coalesce';
  version: number | null;
  lastRunAt: string | null;
  lastRunId: string | null;
  lastStatus: string | null;
  lastError: string | null;
  nextRunAt: string | null;
  createdAt: string;
  updatedAt: string;
}

type Row = {
  id: string; workflowId: string; name: string; cron: string; timezone: string;
  enabled: boolean; catchUp: string; version: number | null;
  lastRunAt: Date | null; lastRunId: string | null; lastStatus: string | null;
  lastError: string | null; nextRunAt: Date | null; createdAt: Date; updatedAt: Date;
};

function toRecord(row: Row): ScheduleRecord {
  return {
    id: row.id,
    workflowId: row.workflowId,
    name: row.name,
    cron: row.cron,
    timezone: row.timezone,
    enabled: row.enabled,
    catchUp: row.catchUp === 'coalesce' ? 'coalesce' : 'skip',
    version: row.version,
    lastRunAt: row.lastRunAt?.toISOString() ?? null,
    lastRunId: row.lastRunId,
    lastStatus: row.lastStatus,
    lastError: row.lastError,
    nextRunAt: row.nextRunAt?.toISOString() ?? null,
    createdAt: row.createdAt.toISOString(),
    updatedAt: row.updatedAt.toISOString(),
  };
}

export function computeNextRun(cron: string, timezone: string, from = new Date()): Date | null {
  return nextRunAt(cron, timezone, from);
}

export async function listSchedules(workflowId?: string): Promise<ScheduleRecord[]> {
  const rows = await prisma.workflowSchedule.findMany({
    where: workflowId ? { workflowId } : {},
    orderBy: { createdAt: 'asc' },
    take: 200,
  });
  return rows.map((r) => toRecord(r as Row));
}

export async function createSchedule(input: {
  workflowId: string;
  name: string;
  cron: string;
  timezone?: string;
  catchUp?: 'skip' | 'coalesce';
  version?: number | null;
  enabled?: boolean;
}): Promise<ScheduleRecord> {
  if (!isValidCron(input.cron)) throw new Error(`Invalid cron expression: ${input.cron}`);
  const timezone = input.timezone ?? 'UTC';
  const next = computeNextRun(input.cron, timezone);
  if (!next) throw new Error('That expression never matches — use one that fires within 40 days.');
  const row = await prisma.workflowSchedule.create({
    data: {
      workflowId: input.workflowId,
      name: input.name,
      cron: input.cron.trim(),
      timezone,
      catchUp: input.catchUp ?? 'skip',
      version: input.version ?? null,
      enabled: input.enabled ?? true,
      nextRunAt: next,
    },
  });
  return toRecord(row as Row);
}

export async function updateSchedule(
  id: string,
  patch: Partial<Pick<ScheduleRecord, 'name' | 'cron' | 'timezone' | 'enabled' | 'catchUp' | 'version'>>,
): Promise<ScheduleRecord | null> {
  const existing = await prisma.workflowSchedule.findUnique({ where: { id } });
  if (!existing) return null;
  const cron = patch.cron?.trim() ?? existing.cron;
  const timezone = patch.timezone ?? existing.timezone;
  if (patch.cron) {
    if (!isValidCron(cron)) throw new Error(`Invalid cron expression: ${cron}`);
    parseCron(cron); // surfaces field-level errors early
  }
  const enabled = patch.enabled ?? existing.enabled;
  const next = enabled ? computeNextRun(cron, timezone) : null;
  if (enabled && !next) throw new Error('That expression never matches — use one that fires within 40 days.');
  const row = await prisma.workflowSchedule.update({
    where: { id },
    data: {
      name: patch.name ?? existing.name,
      cron,
      timezone,
      enabled,
      catchUp: patch.catchUp ?? existing.catchUp,
      version: patch.version === undefined ? existing.version : patch.version,
      // Changing when a schedule fires recomputes the next occurrence.
      ...(patch.cron || patch.timezone || patch.enabled !== undefined ? { nextRunAt: next } : {}),
    },
  });
  return toRecord(row as Row);
}

export async function deleteSchedule(id: string): Promise<boolean> {
  try {
    await prisma.workflowSchedule.delete({ where: { id } });
    return true;
  } catch {
    return false;
  }
}

/** Schedules whose next fire time has arrived. */
export async function dueSchedules(now = new Date()): Promise<ScheduleRecord[]> {
  const rows = await prisma.workflowSchedule.findMany({
    where: { enabled: true, nextRunAt: { lte: now } },
    orderBy: { nextRunAt: 'asc' },
    take: 50,
  });
  return rows.map((r) => toRecord(r as Row));
}

/** Record the outcome of one fire and advance the schedule. */
export async function recordScheduleRun(
  id: string,
  outcome: { runId?: string | null; status: string; error?: string | null },
  firedAt = new Date(),
): Promise<ScheduleRecord | null> {
  const existing = await prisma.workflowSchedule.findUnique({ where: { id } });
  if (!existing) return null;
  // Advance strictly past the fire time so a slow tick cannot double-fire.
  const next = computeNextRun(existing.cron, existing.timezone, firedAt);
  const row = await prisma.workflowSchedule.update({
    where: { id },
    data: {
      lastRunAt: firedAt,
      lastRunId: outcome.runId ?? null,
      lastStatus: outcome.status,
      lastError: outcome.error ?? null,
      nextRunAt: next,
    },
  });
  return toRecord(row as Row);
}

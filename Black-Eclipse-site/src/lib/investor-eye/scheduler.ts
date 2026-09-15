// ── Investor Eye — ingestion scheduler ───────────────────────────────────────
// Background refresh of the world state, mirroring the discipline of the other
// in-process crons (`scraper/scheduler.ts`, `connectors/refresh-scheduler.ts`):
// a single cron, a boot grace period, a mutex, and it yields to the scraper's
// synchronous whole-market writes rather than competing for SQLite.
//
// Cadence: GDELT/USGS are public and rate-limited, so the default is 10 minutes
// (the assembled state itself is also served from a 3-minute SWR cache).

import cron, { ScheduledTask } from "node-cron";
import { prisma } from "@/lib/db";
import { syncBusy } from "@/lib/scraper/scheduler";
import { assembleState } from "./state";

export const INVESTOR_EYE_REFRESH_TYPE = "investor_eye_refresh";
const DEFAULT_INTERVAL_MIN = 10;
const MIN_INTERVAL_MIN = 5;
const BOOT_GRACE_MS = 2 * 60 * 1000;

let task: ScheduledTask | null = null;
let running = false;
let lastRunAt: Date | null = null;
let lastError: string | null = null;

export function investorEyeBusy(): boolean {
  return running;
}

export function investorEyeStatus(): { lastRunAt: Date | null; lastError: string | null; busy: boolean } {
  return { lastRunAt, lastError, busy: running };
}

/** Run one ingestion cycle. Never throws. */
export async function runInvestorEyeIngest(hours = 24): Promise<{ ok: boolean; events: number; error?: string }> {
  if (running) return { ok: false, events: 0, error: "already running" };
  if (syncBusy()) return { ok: false, events: 0, error: "scraper write path busy" };
  running = true;
  try {
    const state = await assembleState({ hours, force: true });
    lastRunAt = new Date();
    lastError = state.eventsUnavailable ? "all sources unavailable" : null;
    await prisma.cronJob.upsert({
      where: { type: INVESTOR_EYE_REFRESH_TYPE },
      update: { lastRunAt, enabled: true },
      create: { type: INVESTOR_EYE_REFRESH_TYPE, lastRunAt, intervalMinutes: DEFAULT_INTERVAL_MIN, enabled: true },
    });
    return { ok: !state.eventsUnavailable, events: state.events.length, error: lastError ?? undefined };
  } catch (err) {
    lastError = err instanceof Error ? err.message : String(err);
    console.error("[InvestorEye] ingest failed:", err);
    return { ok: false, events: 0, error: lastError };
  } finally {
    running = false;
  }
}

/** Start the cron. Called once at app startup. */
export async function startInvestorEyeIngest(): Promise<void> {
  if (task) return;
  try {
    await prisma.cronJob.upsert({
      where: { type: INVESTOR_EYE_REFRESH_TYPE },
      update: {},
      create: { type: INVESTOR_EYE_REFRESH_TYPE, intervalMinutes: DEFAULT_INTERVAL_MIN, enabled: true },
    });
  } catch (err) {
    console.error("[InvestorEye] init failed:", err);
  }

  const bootTime = Date.now();
  task = cron.schedule("*/5 * * * *", async () => {
    try {
      if (Date.now() - bootTime < BOOT_GRACE_MS) return;
      const job = await prisma.cronJob.findUnique({ where: { type: INVESTOR_EYE_REFRESH_TYPE } });
      if (!(job?.enabled ?? true)) return;
      const intervalMs = Math.max(job?.intervalMinutes ?? DEFAULT_INTERVAL_MIN, MIN_INTERVAL_MIN) * 60_000;
      const last = job?.lastRunAt?.getTime() ?? 0;
      if (Date.now() - last < intervalMs) return;
      const result = await runInvestorEyeIngest();
      console.log(`[InvestorEye] refresh: ${result.ok ? `${result.events} events` : result.error}`);
    } catch (err) {
      lastError = err instanceof Error ? err.message : String(err);
      console.error("[InvestorEye] cycle error:", err);
    }
  });
}

export function stopInvestorEyeIngest(): void {
  if (task) {
    task.stop();
    task = null;
  }
}

/** Test seam. */
export function resetInvestorEyeState(): void {
  running = false;
  lastRunAt = null;
  lastError = null;
}

// ── Journal broker auto-sync ─────────────────────────────────────────────────
// A single background timer, opt-in per link (`JournalBrokerLink.autoSync`).
// It never runs a broker mutation and never invents a trade: it calls the same
// `syncJournalBroker` path the manual button uses.
//
// A disconnected terminal is expected, not exceptional. Failures get an
// in-memory backoff so a down broker is not hammered every tick.

import { prisma } from "@/lib/db";
import { syncJournalBroker } from "./sync";

const DEFAULT_INTERVAL_SECONDS = 300;
const MIN_INTERVAL_SECONDS = 60;
const FAILURE_BACKOFF_MS = 5 * 60_000;

interface SchedulerGlobal {
  __journalBrokerTimer?: ReturnType<typeof setInterval>;
  __journalBrokerRunning?: boolean;
  __journalBrokerRetryAt?: Map<string, number>;
}

const g = globalThis as unknown as SchedulerGlobal;
const retryAt = (g.__journalBrokerRetryAt ??= new Map<string, number>());

/** Pure: is this link due for an automatic sync? */
export function isAutoSyncDue(
  link: { autoSync: boolean; enabled: boolean; lastSyncedAt: string | null },
  nowMs: number,
  intervalMs: number,
): boolean {
  if (!link.autoSync || !link.enabled) return false;
  if (!link.lastSyncedAt) return true;
  const last = Date.parse(link.lastSyncedAt);
  if (!Number.isFinite(last)) return true;
  return nowMs - last >= intervalMs;
}

function intervalMs(): number {
  const raw = Number(process.env.JOURNAL_BROKER_SYNC_SECONDS ?? DEFAULT_INTERVAL_SECONDS);
  if (!Number.isFinite(raw) || raw <= 0) return 0;
  return Math.max(MIN_INTERVAL_SECONDS, Math.round(raw)) * 1000;
}

async function tick(): Promise<void> {
  if (g.__journalBrokerRunning) return;
  const every = intervalMs();
  if (every === 0) return;
  g.__journalBrokerRunning = true;
  try {
    const links = await prisma.journalBrokerLink.findMany({
      where: { enabled: true, autoSync: true },
      select: { profileId: true, connectionId: true, lastSyncedAt: true },
    });
    const now = Date.now();
    for (const link of links) {
      const due = isAutoSyncDue(
        {
          autoSync: true,
          enabled: true,
          lastSyncedAt: link.lastSyncedAt ? link.lastSyncedAt.toISOString() : null,
        },
        now,
        every,
      );
      const backoffUntil = retryAt.get(link.connectionId) ?? 0;
      if (!due || now < backoffUntil) continue;

      const summary = await syncJournalBroker(link.profileId, link.connectionId);
      if (summary.ok) {
        retryAt.delete(link.connectionId);
        if (summary.imported > 0 || summary.updated > 0) {
          console.log(
            `[journal-broker] ${link.connectionId}: ${summary.imported} new, ${summary.updated} updated`,
          );
        }
      } else {
        retryAt.set(link.connectionId, Date.now() + FAILURE_BACKOFF_MS);
        console.warn(`[journal-broker] ${link.connectionId}: ${summary.error ?? summary.status}`);
      }
    }
  } catch (err) {
    console.error("[journal-broker] auto-sync tick failed:", err);
  } finally {
    g.__journalBrokerRunning = false;
  }
}

/**
 * Start the one timer. Idempotent: instrumentation can be evaluated twice, and
 * this must never create two loops over the same broker terminal.
 */
export function startJournalBrokerSync(): void {
  if (g.__journalBrokerTimer) return;
  const every = intervalMs();
  if (every === 0) {
    console.log("[journal-broker] auto-sync disabled (JOURNAL_BROKER_SYNC_SECONDS=0)");
    return;
  }
  g.__journalBrokerTimer = setInterval(() => {
    void tick();
  }, every);
  // Do not hold the process open (serverless / test shutdown).
  g.__journalBrokerTimer.unref?.();
  console.log(`[journal-broker] auto-sync timer every ${every / 1000}s`);
}

/** Test/shutdown hook. */
export function stopJournalBrokerSync(): void {
  if (g.__journalBrokerTimer) clearInterval(g.__journalBrokerTimer);
  g.__journalBrokerTimer = undefined;
  g.__journalBrokerRunning = false;
  retryAt.clear();
}

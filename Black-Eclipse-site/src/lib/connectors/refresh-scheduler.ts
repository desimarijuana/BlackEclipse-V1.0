// ── Dataset refresh scheduler ───────────────────────────────────────────────
// Background cron that re-pulls datasets with `refreshEnabled`. Mirrors the
// patterns in `scraper/scheduler.ts` deliberately: a single in-process cron,
// a boot grace period, a per-item "due" check, and a mutex so two heavy jobs
// never run at once. better-sqlite3 is synchronous, so runs are spaced out and
// skipped entirely while the scraper/universe-sync owns the write path.

import cron, { ScheduledTask } from "node-cron";
import { prisma } from "@/lib/db";
import { pullDataset, type PullSummary } from "./refresh";
import { syncBusy } from "@/lib/scraper/scheduler";

export const DATASET_REFRESH_TYPE = "dataset_refresh";
const MIN_INTERVAL_MIN = 5;
const BOOT_GRACE_MS = 90 * 1000;

let task: ScheduledTask | null = null;
let running = false;
/** Bounded record of the most recent run, surfaced to the UI. */
let lastRunAt: Date | null = null;
let lastError: string | null = null;

export function datasetRefreshBusy(): boolean {
  return running;
}

export function datasetRefreshStatus(): { lastRunAt: Date | null; lastError: string | null; busy: boolean } {
  return { lastRunAt, lastError, busy: running };
}

/**
 * Refresh every dataset that is due. Sequential on purpose — parallel pulls
 * would fan out concurrent outbound requests and synchronous SQLite writes.
 */
export async function runDueDatasetRefreshes(
  options: { force?: boolean; now?: Date } = {}
): Promise<{ considered: number; refreshed: number; failed: number; summaries: Array<{ name: string; summary?: PullSummary; error?: string }> }> {
  if (running) return { considered: 0, refreshed: 0, failed: 0, summaries: [] };
  // Never compete with the scraper's whole-market write storms.
  if (!options.force && syncBusy()) return { considered: 0, refreshed: 0, failed: 0, summaries: [] };

  running = true;
  const now = options.now ?? new Date();
  const summaries: Array<{ name: string; summary?: PullSummary; error?: string }> = [];
  let refreshed = 0;
  let failed = 0;

  try {
    const datasets = await prisma.customDataset.findMany({
      where: { refreshEnabled: true, connectorId: { not: null } },
    });

    const due = datasets.filter((d) => {
      if (options.force) return true;
      const last = d.lastRefreshAt?.getTime() ?? 0;
      const intervalMs = Math.max(d.refreshIntervalMin, MIN_INTERVAL_MIN) * 60_000;
      return now.getTime() - last >= intervalMs;
    });

    for (const dataset of due) {
      try {
        const summary = await pullDataset(dataset.id, { now });
        if (summary.failed > 0 && summary.succeeded === 0) {
          failed++;
          summaries.push({ name: dataset.name, summary, error: summary.results[0]?.error });
        } else {
          refreshed++;
          summaries.push({ name: dataset.name, summary });
        }
        const intervalMs = Math.max(dataset.refreshIntervalMin, MIN_INTERVAL_MIN) * 60_000;
        await prisma.customDataset.update({
          where: { id: dataset.id },
          data: {
            lastRefreshAt: now,
            nextRefreshAt: new Date(now.getTime() + intervalMs),
          },
        });
      } catch (err) {
        failed++;
        const message = err instanceof Error ? err.message : String(err);
        summaries.push({ name: dataset.name, error: message });
        // Still advance the clock so a permanently broken dataset does not
        // retry on every single tick.
        const intervalMs = Math.max(dataset.refreshIntervalMin, MIN_INTERVAL_MIN) * 60_000;
        await prisma.customDataset
          .update({
            where: { id: dataset.id },
            data: { lastRefreshAt: now, nextRefreshAt: new Date(now.getTime() + intervalMs) },
          })
          .catch(() => {});
      }
    }

    lastRunAt = now;
    lastError = failed > 0 ? `${failed} dataset(s) failed` : null;
    if (datasets.length > 0) {
      await prisma.cronJob.upsert({
        where: { type: DATASET_REFRESH_TYPE },
        update: { lastRunAt: now, enabled: true },
        create: { type: DATASET_REFRESH_TYPE, lastRunAt: now, intervalMinutes: 15, enabled: true },
      });
    }
    return { considered: datasets.length, refreshed, failed, summaries };
  } finally {
    running = false;
  }
}

/** Start the dataset-refresh cron. Called once at app startup. */
export async function startDatasetRefresh(): Promise<void> {
  if (task) return;
  try {
    await prisma.cronJob.upsert({
      where: { type: DATASET_REFRESH_TYPE },
      update: {},
      create: { type: DATASET_REFRESH_TYPE, intervalMinutes: 15, enabled: true },
    });
  } catch (err) {
    console.error("[DatasetRefresh] init failed:", err);
  }

  const bootTime = Date.now();
  // Same cadence as the price scheduler: poll every minute, run what is due.
  task = cron.schedule("* * * * *", async () => {
    try {
      if (Date.now() - bootTime < BOOT_GRACE_MS) return;
      const job = await prisma.cronJob.findUnique({ where: { type: DATASET_REFRESH_TYPE } });
      if (!(job?.enabled ?? true)) return;
      const result = await runDueDatasetRefreshes();
      if (result.refreshed > 0 || result.failed > 0) {
        console.log(`[DatasetRefresh] refreshed ${result.refreshed}, failed ${result.failed}`);
      }
    } catch (err) {
      lastError = err instanceof Error ? err.message : String(err);
      console.error("[DatasetRefresh] cycle error:", err);
    }
  });
}

export function stopDatasetRefresh(): void {
  if (task) {
    task.stop();
    task = null;
  }
}

/** Test seam: reset in-memory run state. */
export function resetDatasetRefreshState(): void {
  running = false;
  lastRunAt = null;
  lastError = null;
}

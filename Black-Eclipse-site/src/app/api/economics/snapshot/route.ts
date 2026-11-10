import { NextResponse } from "next/server";
import { buildSnapshot, type SnapshotMetric } from "@/lib/economics/snapshot";
import { readLastGood, writeLastGood } from "@/lib/economics/state-cache";

export const dynamic = "force-dynamic";
export const maxDuration = 60;

// In-memory SWR cache — central-bank rates and CPI prints move slowly.
const CACHE_TTL_MS = 10 * 60 * 1000;
type SnapshotPayload = { metrics: SnapshotMetric[]; builtAt: string };
let cache: { t: number; data: SnapshotPayload } | null = null;
let rebuildInFlight = false;

/**
 * Fill a fresh snapshot's gaps from the last known good payload and persist the
 * merged result. A value that a provider returned is never overwritten; only a
 * `null` is backfilled, and it is relabelled CACHED with its confirmation date.
 */
async function withLastKnownGood(fresh: SnapshotPayload): Promise<SnapshotPayload> {
  const last = await readLastGood<SnapshotPayload>("snapshot");
  if (!last) {
    await writeLastGood("snapshot", fresh);
    return fresh;
  }

  const previous = new Map(last.data.metrics.map((m) => [m.id, m]));
  const merged = fresh.metrics.map((metric): SnapshotMetric => {
    if (metric.value !== null) return metric;
    const cached = previous.get(metric.id);
    if (!cached || cached.value === null) return metric;
    return {
      ...metric,
      value: cached.value,
      asOf: cached.asOf,
      unit: cached.unit,
      source: `CACHED · ${cached.source}`,
      state: "CACHED",
      url: cached.url ?? null,
      cachedAt: last.savedAt,
    };
  });

  const payload = { ...fresh, metrics: merged };
  await writeLastGood("snapshot", payload);
  return payload;
}

function startBackgroundRebuild() {
  if (rebuildInFlight) return;
  rebuildInFlight = true;
  buildSnapshot()
    .then(withLastKnownGood)
    .then((data) => { cache = { t: Date.now(), data }; })
    .catch((err) => console.error("[api/economics/snapshot] background rebuild:", err))
    .finally(() => { rebuildInFlight = false; });
}

// GET /api/economics/snapshot?refresh=1 — key central-bank rates + key prints
// with vintage. `refresh=1` bypasses the SWR cache and rebuilds from providers.
export async function GET(request: Request) {
  const force = new URL(request.url).searchParams.get("refresh") === "1";
  try {
    if (!force && cache) {
      if (Date.now() - cache.t < CACHE_TTL_MS) return NextResponse.json(cache.data);
      startBackgroundRebuild();
      return NextResponse.json(cache.data);
    }
    const data = await withLastKnownGood(await buildSnapshot());
    cache = { t: Date.now(), data };
    return NextResponse.json(data);
  } catch (err) {
    console.error("[api/economics/snapshot] GET error:", err);
    const last = await readLastGood<SnapshotPayload>("snapshot");
    if (last) return NextResponse.json(last.data);
    return NextResponse.json({ metrics: [], builtAt: new Date().toISOString() }, { status: 500 });
  }
}

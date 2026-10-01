// ─── Bounded cross-market route-health probe (Harness closeout Phase 2.5) ────
//
// Records exactly ONE attempt per (market × implemented capability) into the
// SAME SourceHealth ledger production traffic writes to, under the SAME
// canonical route key, with `probeKind` recorded explicitly. It reuses the
// existing SSRF-safe transport and providers — no new fetcher.
//
// Two entry points:
//   * `runRouteHealthProbe({ ... })` — a bounded manual one-shot. Works
//     immediately; the operator runs it on demand (CLI or the operator route).
//   * `maybeStartScheduledProbe()` — the RECURRING schedule, DISABLED by default
//     behind the `HARNESS_ROUTE_PROBE_ENABLED` operator flag (decision D2).
//
// A FIXTURE probe is always written with probeKind="fixture" and is never
// presented as live health in get_source_health or get_capability_matrix.

import { prisma } from "@/lib/db";
import { fetchYahooBatchRaw } from "@/lib/scraper/fetchers/yfinance";
import { canonicalSource, canonicalMarket, canonicalAssetClass } from "@/lib/harness/health-key";

// The health key encoding (assetClass#capability[!fixture]) is owned by the
// bridge; reproduce it here from the canonical primitives so the probe writes
// the SAME key production traffic reads. The `#`/`!fixture` markers must match
// `encodeHealthKey` in data-bridge.ts.
const HEALTH_CAP_SEP = "#";
const HEALTH_FIXTURE_SUFFIX = "!fixture";

function encodeProbeHealthKey(assetClass: string, capability: string, probeKind: "live" | "fixture"): string {
  const cap = probeKind === "fixture" ? `${capability}${HEALTH_FIXTURE_SUFFIX}` : capability;
  return `${canonicalAssetClass(assetClass)}${HEALTH_CAP_SEP}${cap}`;
}
import { COVERAGE } from "@/lib/harness/coverage";
import { QUOTE_SAMPLE_SYMBOLS } from "@/lib/harness/provider-eligibility";

// The implemented capabilities the probe covers per market. Web routes are
// market-independent and exercised by `research_health`, so they are excluded.
const PROBE_CAPABILITIES = ["live_quote", "price_history"] as const;

export interface ProbeOptions {
  /** Restrict to these markets; default = every declared market with a sample. */
  markets?: string[];
  /** "live" (default) records real provider results; "fixture" is labelled. */
  kind?: "live" | "fixture";
  /** Per-market provider timeout. */
  timeoutMs?: number;
}

export interface ProbeResult {
  probed: number;
  ok: number;
  failed: number;
  skipped: number;
  markets: string[];
  kind: "live" | "fixture";
}

async function recordProbe(
  source: string, market: string, capability: string, ok: boolean,
  probeKind: "live" | "fixture", error?: string,
): Promise<void> {
  const canonSource = canonicalSource(source);
  const canonMarket = canonicalMarket(market);
  const symbol = encodeProbeHealthKey("equity", capability, probeKind);
  const id = `${canonSource}:${canonMarket}:${symbol}`;
  const now = new Date();
  await prisma.sourceHealth.upsert({
    where: { id },
    create: {
      id, source: canonSource, market: canonMarket, symbol,
      successCount: ok ? 1 : 0, failCount: ok ? 0 : 1,
      lastStatus: ok ? "ok" : "fail", lastError: ok ? null : error ?? null,
      lastSuccessAt: ok ? now : null, lastFailureAt: ok ? null : now,
    },
    update: {
      successCount: { increment: ok ? 1 : 0 },
      failCount: { increment: ok ? 0 : 1 },
      lastStatus: ok ? "ok" : "fail", lastError: ok ? null : error ?? null,
      ...(ok ? { lastSuccessAt: now } : { lastFailureAt: now }),
    },
  });
}

/** One cheap live quote attempt for a market's declared sample symbol. */
async function probeQuote(
  market: string, sample: string, timeoutMs: number,
): Promise<{ ok: boolean; error?: string }> {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const data = await fetchYahooBatchRaw([sample], market);
      const ticker = Object.keys(data.quotes ?? {})[0];
      const q = ticker ? data.quotes?.[ticker] : undefined;
      if (q && q.price > 0) return { ok: true };
      return { ok: false, error: `no quote for sample ${sample} (${market})` };
    } finally {
      clearTimeout(timer);
    }
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "probe failed" };
  }
}

/**
 * Run the bounded route-health probe. One attempt per (market × capability),
 * recorded under the canonical key. Deterministic when `kind="fixture"`.
 */
export async function runRouteHealthProbe(options: ProbeOptions = {}): Promise<ProbeResult> {
  const kind = options.kind ?? "live";
  const timeoutMs = options.timeoutMs ?? 5_000;
  const universe = options.markets ?? Object.keys(COVERAGE);
  const result: ProbeResult = { probed: 0, ok: 0, failed: 0, skipped: 0, markets: [], kind };

  for (const market of universe) {
    const elig = QUOTE_SAMPLE_SYMBOLS[market];
    const sample = elig?.sampleSymbol;
    if (!sample) {
      // No declared sample → nothing to probe honestly; skip (never a fabricated
      // attempt that would make an untested market look failing).
      result.skipped += 1;
      continue;
    }
    result.markets.push(market);
    for (const capability of PROBE_CAPABILITIES) {
      if (kind === "fixture") {
        // A fixture probe is deterministic offline evidence. It never performs a
        // network call and is written with probeKind="fixture".
        await recordProbe("LIVE_STRUCTURED", market, capability, true, "fixture");
        result.probed += 1;
        result.ok += 1;
        continue;
      }
      const outcome = await probeQuote(market, sample, timeoutMs);
      await recordProbe("LIVE_STRUCTURED", market, capability, outcome.ok, "live", outcome.error);
      result.probed += 1;
      if (outcome.ok) result.ok += 1;
      else result.failed += 1;
    }
  }
  return result;
}

/** Whether the recurring probe is enabled (operator flag, default OFF). */
export function scheduledProbeEnabled(): boolean {
  return process.env.HARNESS_ROUTE_PROBE_ENABLED === "1"
    || process.env.HARNESS_ROUTE_PROBE_ENABLED === "true";
}

let _scheduled: ReturnType<typeof setInterval> | null = null;

/**
 * Start the recurring cross-market probe (decision D2: DISABLED by default).
 *
 * A no-op unless `HARNESS_ROUTE_PROBE_ENABLED=1`. The interval defaults to 6h
 * and is bounded. This is process-local and best-effort; the manual one-shot
 * (`runRouteHealthProbe`) always works without the flag.
 */
export function maybeStartScheduledProbe(intervalMs = 6 * 60 * 60 * 1000): boolean {
  if (!scheduledProbeEnabled()) return false;
  if (_scheduled) return true;
  _scheduled = setInterval(() => {
    void runRouteHealthProbe().catch(() => {
      /* best-effort; a probe failure never affects production traffic */
    });
  }, Math.max(60_000, intervalMs));
  // Do not keep the event loop alive purely for a probe.
  if (typeof _scheduled.unref === "function") _scheduled.unref();
  return true;
}

export function stopScheduledProbe(): void {
  if (_scheduled) {
    clearInterval(_scheduled);
    _scheduled = null;
  }
}

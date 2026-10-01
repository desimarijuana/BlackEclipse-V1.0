// --- Route-health ledger surface (Harness closeout Phase 2) ------------------
// The ONE writer and the two readers of the SourceHealth ledger:
//   * encodeHealthKey / decodeHealthKey - the `<assetClass>#<capability>[!fixture]`
//     key format (kept in `symbol` so health is keyed per capability without a
//     schema change to the committed DB).
//   * recordHealth - the single upsert seam every recorded attempt passes.
//   * recordCapabilityHealth - derives the canonical route key from a capability
//     result and records it (called once at the `fetchCapability` boundary).
//   * sourceHealth - the summary-partitioned reader (recorded head first; the
//     ~1,200-row declared list is opt-in, never the default).
//   * coverageCapability / routeProbe - the coverage summary and the manual
//     cross-market probe capability.
//
// Extracted from data-bridge.ts to keep that file under its size ratchet. It owns
// the ledger contract; data-bridge re-exports what its callers/tests import.

import { prisma } from "@/lib/db";
import { coverageSummary, allHealthTargets } from "@/lib/harness/coverage";
import {
  canonicalMarket,
  canonicalAssetClass,
  canonicalSource,
  HEALTH_CAPABILITY,
  DEFAULT_HEALTH_SOURCE,
} from "@/lib/harness/health-key";
import type { DataBridgeResult } from "@/lib/harness/data-bridge-types";

export type { DataBridgeResult };

const HEALTH_CAP_SEP = "#";
const HEALTH_FIXTURE_SUFFIX = "!fixture";

export function encodeHealthKey(assetClass: string, capability: string, probeKind: "live" | "fixture"): string {
  const cap = probeKind === "fixture" ? `${capability}${HEALTH_FIXTURE_SUFFIX}` : capability;
  return `${canonicalAssetClass(assetClass)}${HEALTH_CAP_SEP}${cap}`;
}

export function decodeHealthKey(symbol: string): { assetClass: string; capability: string; probeKind: "live" | "fixture" } {
  const idx = symbol.indexOf(HEALTH_CAP_SEP);
  if (idx === -1) {
    // Legacy row: assetClass only, treated as a live quote probe.
    return { assetClass: symbol, capability: "quote", probeKind: "live" };
  }
  // Normalise on read too: rows written before normalisation existed may carry
  // a raw asset class ("Equity") or a non-route "unknown"; they must fold onto
  // the same canonical key as fresh writes, not form a parallel row.
  const assetClass = canonicalAssetClass(symbol.slice(0, idx));
  let cap = symbol.slice(idx + 1);
  let probeKind: "live" | "fixture" = "live";
  if (cap.endsWith(HEALTH_FIXTURE_SUFFIX)) {
    cap = cap.slice(0, -HEALTH_FIXTURE_SUFFIX.length);
    probeKind = "fixture";
  }
  return { assetClass, capability: cap || "quote", probeKind };
}

export async function recordHealth(
  source: string,
  market: string,
  assetClass: string,
  ok: boolean,
  error?: string,
  capability: string = "quote",
  probeKind: "live" | "fixture" = "live",
): Promise<void> {
  try {
    // Normalise the route dimensions so one real route maps to one row
    // (P1-5) — casing and unresolved values must never fragment the ledger.
    const canonSource = canonicalSource(source);
    const canonMarket = canonicalMarket(market);
    const symbol = encodeHealthKey(assetClass, capability, probeKind);
    const id = `${canonSource}:${canonMarket}:${symbol}`;
    const now = new Date();
    await prisma.sourceHealth.upsert({
      where: { id },
      create: {
        id,
        source: canonSource,
        market: canonMarket,
        symbol,
        successCount: ok ? 1 : 0,
        failCount: ok ? 0 : 1,
        lastStatus: ok ? "ok" : "fail",
        lastError: ok ? null : error ?? null,
        // Per-route stamps: separate success from failure so "failing now" is
        // distinguishable from "succeeded earlier then failed transiently".
        lastSuccessAt: ok ? now : null,
        lastFailureAt: ok ? null : now,
      },
      update: {
        successCount: { increment: ok ? 1 : 0 },
        failCount: { increment: ok ? 0 : 1 },
        lastStatus: ok ? "ok" : "fail",
        lastError: ok ? null : error ?? null,
        ...(ok ? { lastSuccessAt: now } : { lastFailureAt: now }),
      },
    });
  } catch {
    /* health is best-effort */
  }
}


// Capabilities that are not about one instrument (news, web research), so their
// route key uses the existing `*` wildcard rather than a per-instrument class.
const INSTRUMENT_LESS_CAPABILITIES: ReadonlySet<string> = new Set([
  "news",
  "web_search",
  "web_fetch",
]);

/**
 * Derive the canonical route key from a capability + its result and record the
 * outcome. Source/market/assetClass come from the result when it carries them
 * (provenance fields), from an explicit `healthContext` on a failure, else from
 * a per-capability default or `unknown`. `unknown` is honest: a request that
 * never resolved its instrument is a failed attempt, not a healthy route.
 */
export async function recordCapabilityHealth(
  capability: string,
  params: Record<string, unknown>,
  result: DataBridgeResult
): Promise<void> {
  const healthCap = HEALTH_CAPABILITY[capability];
  if (!healthCap) return; // unmapped → do not guess a route
  const instrumentLess = INSTRUMENT_LESS_CAPABILITIES.has(capability);
  const ok = result.status === "OK";
  const ctx = (result.healthContext as { source?: string; market?: string; assetClass?: string } | undefined) ?? {};
  const source =
    (typeof result.provider === "string" && result.provider) ||
    (typeof result.priceSource === "string" && result.priceSource) ||
    ctx.source ||
    DEFAULT_HEALTH_SOURCE[capability] ||
    "unknown";
  const market = instrumentLess
    ? "*"
    : (typeof result.market === "string" && result.market) ||
      (typeof result.country === "string" && result.country) ||
      ctx.market ||
      (typeof params.market === "string" && params.market) ||
      "unknown";
  const assetClass = instrumentLess
    ? "*"
    : (typeof result.assetClass === "string" && result.assetClass) ||
      ctx.assetClass ||
      "unknown";
  const error = ok ? undefined : (typeof result.error === "string" ? result.error : undefined);
  // Canonicalise the route identity BEFORE recording so two observations of the
  // same real route cannot land on two rows (P1-5). An unresolved market or
  // asset class becomes the wildcard `*`, never a persisted "unknown".
  await recordHealth(
    canonicalSource(source),
    canonicalMarket(String(market)),
    canonicalAssetClass(String(assetClass)),
    ok,
    error,
    healthCap
  );
}


export async function sourceHealth(params: Record<string, unknown> = {}): Promise<DataBridgeResult> {
  const recordedOnly = params.recordedOnly === true;
  const includeDeclared = params.includeDeclared === true;
  const headLimit = Math.min(Math.max(Number(params.limit ?? 25) || 25, 1), 100);
  const rows = await prisma.sourceHealth.groupBy({
    by: ["source", "market", "symbol"],
    _sum: { successCount: true, failCount: true },
    _max: {
      lastStatus: true, updatedAt: true,
      // Per-route stamps (Phase 2). Absent on an older DB → null, which the row
      // reports honestly rather than guessing a success from updatedAt.
      lastSuccessAt: true, lastFailureAt: true,
    } as Record<string, boolean>,
  });

  // ── Key health by the dimensions that actually identify a route ────────────
  // A route is (source × market × assetClass × CAPABILITY × probe-kind). Each
  // recorded run is kept distinct; a declared-but-unrun target is `unknown`.
  // A working quote can never make a statement route look healthy — they are
  // different rows (WS3). `symbol` encodes assetClass + capability; the
  // decoder preserves legacy assetClass-only rows as `quote`/live.
  interface Stat {
    success: number;
    fail: number;
    updated: string | null;
    lastSuccessAt: string | null;
    lastFailureAt: string | null;
    lastStatus: string | null;
    lastError: string | null;
  }
  const recorded = new Map<string, Stat>();
  const meta = new Map<string, { assetClass: string; capability: string; probeKind: "live" | "fixture" }>();
  const _max = (r: unknown) => (r as { _max: Record<string, Date | string | null> })._max ?? {};
  const _iso = (v: Date | string | null | undefined): string | null =>
    v ? new Date(v).toISOString() : null;
  for (const r of rows) {
    const decoded = r.symbol === "*"
      ? { assetClass: "*", capability: "quote", probeKind: "live" as const }
      : decodeHealthKey(r.symbol);
    // Fold legacy/unnormalised rows onto the canonical route key on read.
    const key = `${canonicalSource(r.source)}|${canonicalMarket(r.market)}|${decoded.assetClass}|${decoded.capability}|${decoded.probeKind}`;
    meta.set(key, decoded);
    const cur = recorded.get(key) ?? {
      success: 0, fail: 0, updated: null, lastSuccessAt: null,
      lastFailureAt: null, lastStatus: null, lastError: null,
    };
    cur.success += r._sum.successCount ?? 0;
    cur.fail += r._sum.failCount ?? 0;
    const mx = _max(r);
    const updated = _iso(mx.updatedAt);
    const successAt = _iso(mx.lastSuccessAt);
    const failureAt = _iso(mx.lastFailureAt);
    if (updated && (!cur.updated || updated > cur.updated)) cur.updated = updated;
    if (successAt && (!cur.lastSuccessAt || successAt > cur.lastSuccessAt)) cur.lastSuccessAt = successAt;
    if (failureAt && (!cur.lastFailureAt || failureAt > cur.lastFailureAt)) cur.lastFailureAt = failureAt;
    recorded.set(key, cur);
  }

  const shape = (t: { source: string; market: string; assetClass: string; capability: string; probeKind: "live" | "fixture" }) => {
    const key = `${t.source}|${t.market}|${t.assetClass}|${t.capability}|${t.probeKind}`;
    const stat = recorded.get(key);
    const success = stat?.success ?? 0;
    const fail = stat?.fail ?? 0;
    const total = success + fail;
    // A declared target with ZERO attempts is `unknown` — NOT healthy, NOT
    // failing. Only recorded runs may claim working/failing.
    const health =
      total === 0 ? "unknown"
        : fail === 0 ? "healthy"
        : success === 0 ? "failing"
        : "degraded";
    const updated = stat?.updated ?? null;
    return {
      source: t.source,
      market: t.market,
      assetClass: t.assetClass,
      capability: t.capability,
      probeKind: t.probeKind,
      // `attempted` mirrors `total` explicitly so a report reader does not have
      // to know the success+fail arithmetic. Everything below is honest about
      // zero-attempt routes: `unknown`, never healthy.
      attempted: total,
      success,
      fail,
      total,
      lastStatus: total === 0 ? null : (fail > 0 && success === 0 ? "fail" : "ok"),
      health,
      // Reliability over the recorded window (0..1); null when never attempted.
      reliability: total === 0 ? null : Math.round((success / total) * 100) / 100,
      successRate: total === 0 ? null : Math.round((success / total) * 100) / 100,
      // Retryable hint: a degraded/failing route may be worth retrying, but we
      // do not claim a specific transient cause from a counter alone.
      retryable: health === "degraded" || health === "failing" ? true : health === "unknown" ? null : false,
      // `updatedAt` is "last attempt". The per-route stamps separate the last
      // SUCCESS from the last FAILURE (Phase 2). Absent on an older DB → null.
      lastAttemptAt: updated,
      updatedAt: updated,
      lastSuccessAt: stat?.lastSuccessAt ?? null,
      lastFailureAt: stat?.lastFailureAt ?? null,
      staleSeconds: updated ? (Date.now() - Date.parse(updated)) / 1000 : null,
      lastError: stat?.lastError ?? null,
      // A fixture probe is deterministic offline evidence and must never be
      // presented as live-provider health.
      sourceOfTruth: t.probeKind === "fixture" ? "fixture" : "live smoke/production",
    };
  };

  // ── Recorded routes (always small, always first) ───────────────────────────
  // The recorded ledger is the only thing that can claim working/failing. It is
  // tiny (tens of rows) and is the honest headline.
  const recordedRows: ReturnType<typeof shape>[] = [];
  for (const key of recorded.keys()) {
    const info = meta.get(key)!;
    const [source, market] = key.split("|");
    recordedRows.push(shape({ source, market, ...info }));
  }

  // ── Summary head: counts by health class + markets with any attempt ────────
  const byHealth = { healthy: 0, degraded: 0, failing: 0, unknown: 0 } as Record<string, number>;
  const marketsWithAttempts = new Set<string>();
  for (const r of recordedRows) {
    byHealth[r.health] = (byHealth[r.health] ?? 0) + 1;
    if (r.total > 0 && r.probeKind === "live" && r.market !== "*") marketsWithAttempts.add(r.market);
  }
  const recordedLive = recordedRows.filter((r) => r.probeKind === "live" && r.total > 0);
  recordedLive.sort((a, b) => b.total - a.total);
  const summary = {
    // Only LIVE recorded rows count as "recorded health"; fixture rows are
    // labelled separately and never presented as live health.
    recordedRoutes: recordedLive.length,
    fixtureRoutes: recordedRows.filter((r) => r.probeKind === "fixture").length,
    byHealth,
    marketsWithAttempts: [...marketsWithAttempts].sort(),
  };

  // `recordedOnly` (or the default shape) must never enumerate the declared
  // universe. It is ~1,200 rows and would swamp the bounded tool result.
  if (recordedOnly) {
    return { status: "OK", summary, rows: recordedLive.length ? recordedLive : [], withheld: 0 };
  }

  // ── Declared-but-unrun enumeration (only when explicitly asked for) ────────
  // ONE target builder (Phase 2.6): the legacy quote axis and the capability
  // axis are a single vocabulary, deduplicated by canonical route key.
  const declared: Array<{ source: string; market: string; assetClass: string; capability: string; probeKind: "live" | "fixture" }> = allHealthTargets();
  const seen = new Set<string>();
  const head = recordedLive.slice(0, headLimit);
  for (const r of head) {
    seen.add(`${r.source}|${r.market}|${r.assetClass}|${r.capability}|${r.probeKind}`);
  }
  const declaredUnrun: ReturnType<typeof shape>[] = [];
  for (const t of declared) {
    const key = `${t.source}|${t.market}|${t.assetClass}|${t.capability}|${t.probeKind}`;
    if (seen.has(key)) continue;
    seen.add(key);
    declaredUnrun.push(shape(t));
  }

  if (includeDeclared) {
    return {
      status: "OK",
      summary,
      rows: [...recordedLive, ...declaredUnrun],
      withheld: 0,
    };
  }
  // Default: a compact, readable head. The full declared list is withheld and
  // the count is stated so a caller can ask for it explicitly.
  return {
    status: "OK",
    summary,
    rows: head,
    withheld: declaredUnrun.length,
  };
}

/** The declared coverage registry, so the system can answer "what do we cover?". */
export function coverageCapability(): DataBridgeResult {
  return { status: "OK", rows: coverageSummary() };
}

/**
 * Bounded cross-market route-health probe (Phase 2.5). Records one attempt per
 * (market × implemented capability) into the SAME ledger, with probeKind
 * explicit. This is the manual one-shot an operator runs; the recurring
 * schedule is gated behind `HARNESS_ROUTE_PROBE_ENABLED` and is OFF by default.
 */
export async function routeProbe(params: Record<string, unknown>): Promise<DataBridgeResult> {
  const { runRouteHealthProbe } = await import("@/lib/harness/route-probe");
  const kind = params.kind === "fixture" ? "fixture" : "live";
  const markets = Array.isArray(params.markets) ? (params.markets as string[]) : undefined;
  const result = await runRouteHealthProbe({
    kind, markets,
    timeoutMs: typeof params.timeoutMs === "number" ? params.timeoutMs : undefined,
  });
  return { status: "OK", ...result };
}

/**
 * The truthful capability matrix. Composes the declared registry with the
 * OBSERVED vault universe sizes and recorded health, and with what each
 * fundamentals/web route needs to be configured. Never advertises a capability
 * from an unrelated one (statements are not implied by quotes).
 */

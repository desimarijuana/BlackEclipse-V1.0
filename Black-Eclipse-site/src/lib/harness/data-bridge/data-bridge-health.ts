// ── Bridge health / diagnostics capabilities ─────────────────────────────────
// Extracted from `data-bridge.ts` (R3-04 split follow-up). These are the
// operator-facing introspection routes: the capability matrix, credential
// presence, and the bounded research-health probe. They never return data
// values; `fetchCapability` excludes them from the health ledger.

import { prisma } from "@/lib/db";
import { secAvailable } from "@/lib/fundamentals/providers/sec-edgar";
import { resolveProviderKey } from "@/lib/provider-keys";
import { buildCapabilityMatrix } from "@/lib/harness/capability";
import { decodeHealthKey, recordHealth } from "@/lib/harness/health-ledger";
import { canonicalMarket, canonicalSource } from "@/lib/harness/health-key";
import { resolveCustomSearchProvider } from "@/lib/harness/web-provider-resolve";
import { resolveSearchProviders } from "@/lib/web-search";
import { searchWeb, fetchWebPageDetailed } from "@/lib/web-research";
import type { RetrievalDiagnostic } from "@/lib/retrieval-diagnostics";
import { unavailableClass } from "@/lib/harness/data-bridge/data-bridge-result";
import type { DataBridgeResult } from "@/lib/harness/data-bridge/data-bridge-types";

export async function capabilityMatrix(): Promise<DataBridgeResult> {
  try {
    // Observed universe sizes per market (an empty vault market reports 0, which
    // is honest; an unreadable DB reports null, which stays "unknown").
    const universeCounts: Record<string, number> = {};
    try {
      const grouped = await prisma.asset.groupBy({ by: ["marketId"], _count: { _all: true } });
      const markets = await prisma.market.findMany({ select: { id: true, country: true } });
      const idToCountry = new Map(markets.map((m) => [m.id, m.country]));
      for (const g of grouped) {
        const country = idToCountry.get(g.marketId);
        if (country) universeCounts[country] = (universeCounts[country] ?? 0) + g._count._all;
      }
    } catch {
      /* leave counts empty — matrix reports null */
    }

    // Observed health PER CAPABILITY from recorded runs (WS3). Each
    // (market × capability) is classified independently so a working quote never
    // marks the statement/filings axis as working. Fixture probe rows are
    // EXCLUDED — only live runs may claim observed working/failing health.
    const observedByCapability: Record<string, "working" | "degraded" | "failing"> = {};
    const liveCheckedMarkets: string[] = [];
    try {
      const rows = await prisma.sourceHealth.groupBy({
        by: ["market", "symbol"],
        _sum: { successCount: true, failCount: true },
      });
      for (const r of rows) {
        const decoded = r.symbol === "*"
          ? { assetClass: "*", capability: "quote", probeKind: "live" as const }
          : decodeHealthKey(r.symbol);
        if (decoded.probeKind === "fixture") continue;
        // Map the internal capability id to a matrix axis name.
        const axis =
          decoded.capability === "live_quote" || decoded.capability === "quote" ? "quote"
            : decoded.capability === "price_history" ? "history"
            : decoded.capability === "fundamentals" || decoded.capability === "financial_statements" ? "fundamentals"
            : decoded.capability === "sec_filings" ? "filings"
            : "web";
        // Canonicalise the market EXACTLY as sourceHealth() does — two readers of
        // one ledger must not disagree (Phase 2). A legacy `unknown` folds to `*`.
        const key = `${canonicalMarket(r.market)}|${axis}`;
        const s = r._sum.successCount ?? 0;
        const f = r._sum.failCount ?? 0;
        // Merge conservatively: any failure keeps a market degraded/failing.
        const current = observedByCapability[key];
        if (s > 0 && f === 0) {
          if (current !== "degraded" && current !== "failing") observedByCapability[key] = "working";
        } else if (s > 0) {
          observedByCapability[key] = "degraded";
        } else if (f > 0) {
          observedByCapability[key] = "failing";
        }
      }
    } catch {
      /* leave observed empty (unknown) */
    }

    // Fundamentals availability: SEC is keyless (US filings); the yfinance bridge
    // is keyless and multi-market; FMP is a keyed multi-market vendor. Coverage
    // is only claimed for a route that is ACTUALLY usable right now.
    let usFilings = false;
    try {
      usFilings = await secAvailable();
    } catch {
      usFilings = false;
    }
    let keylessVendor = false;
    try {
      const { yahooFundamentalsProvider } = await import("@/lib/fundamentals/providers/yahoo");
      keylessVendor = await Promise.resolve(yahooFundamentalsProvider.isConfigured()).catch(() => false);
    } catch {
      keylessVendor = false;
    }
    let multiMarketVendor = false;
    try {
      const fmp = await resolveProviderKey("FINANCIALMODELINGPREP_API_KEY");
      multiMarketVendor = Boolean(fmp && fmp.trim());
    } catch {
      multiMarketVendor = false;
    }

    // A market-level overlay is kept only as a backwards-compatible fallback for
    // markets with no capability-keyed rows yet.
    const observedByMarket: Record<string, "working" | "degraded" | "failing"> = {};
    for (const [key, health] of Object.entries(observedByCapability)) {
      const market = key.split("|")[0];
      const current = observedByMarket[market];
      if (health === "working" && (!current || current === "working")) observedByMarket[market] = "working";
      else if (health === "degraded") observedByMarket[market] = "degraded";
      else if (health === "failing" && current !== "degraded") observedByMarket[market] = current ?? "failing";
    }

    // Web routes are available when the keyless fetch transport is usable (it
    // always is — it is built in); a keyed search provider is an addition.
    const webAvailable = true;

    const matrix = buildCapabilityMatrix({
      universeCounts,
      observedByMarket,
      observedByCapability,
      liveCheckedMarkets,
      fundamentalsAvailability: { usFilings, keylessVendor, multiMarketVendor },
      webAvailable,
    });
    return { status: "OK", rows: matrix };
  } catch (err) {
    return unavailableClass(
      "source_failure",
      `capability matrix failed: ${err instanceof Error ? err.message : String(err)}`,
    );
  }
}

/**
 * Credential PRESENCE for one provider (never the value).
 *
 * The Financial Data Gateway's provider registry needs to know whether a
 * credentialed provider is usable, but a secret must never cross into the Python
 * runtime. This capability answers only `configured` (env or vault) for one env
 * var name — the same masked-status source the Settings UI uses.
 */
export async function providerKeyStatus(params: Record<string, unknown>): Promise<DataBridgeResult> {
  const envVar = String(params.envVar ?? "").trim();
  if (!envVar) return unavailableClass("invalid_request", "envVar is required");
  try {
    const value = await resolveProviderKey(envVar);
    return {
      status: "OK",
      envVar,
      configured: Boolean(value && value.trim()),
    };
  } catch (err) {
    return unavailableClass(
      "source_failure",
      err instanceof Error ? err.message : "provider key status failed",
    );
  }
}

/**
 * A bounded health probe for every research retrieval capability, so an operator
 * can see which route is broken WITHOUT running a research task. Each probe is
 * cheap, SSRF-safe, and reports a structured diagnostic. Never returns a value.
 */
export async function researchHealth(): Promise<DataBridgeResult> {
  const checks: RetrievalDiagnostic[] = [];

  // 1. Web search — one query against the configured provider set.
  const custom = await resolveCustomSearchProvider();
  const providers = await resolveSearchProviders(custom);
  const search = await searchWeb("BlackEclipse research health probe", 3, providers);
  checks.push(...search.diagnostics);

  // 2. Web fetch — a stable, permitted JSON document (the SEC ticker map host).
  const fetchProbe = await fetchWebPageDetailed("https://www.sec.gov/files/company_tickers.json");
  checks.push(fetchProbe.diagnostic);

  // 3. SEC direct — a cheap CIK-map reachability check via the adapter's host.
  const secProbe = await fetchWebPageDetailed(
    "https://data.sec.gov/api/xbrl/companyconcept/CIK0000320193/us-gaap/Revenues.json"
  );
  checks.push({ ...secProbe.diagnostic, provider: "sec-xbrl", tier: "primary" as const });

  // Persist each probe into the SAME ledger production traffic writes to, under
  // the SAME canonical route id (P0-3). A probe and a production run of the same
  // capability must increment ONE row, not two — otherwise the health surface
  // reports a working provider as failing. Probe rows are instrument-less
  // (`*`×`*`) exactly like their production counterparts.
  for (const d of checks) {
    await recordHealth(
      canonicalSource(d.provider),
      "*",
      "*",
      d.normalizedStatus === "ok",
      d.normalizedStatus === "ok" ? undefined : d.detail,
      d.provider === "sec-xbrl" ? "sec_filings" : d.capability
    );
  }

  const capability = (d: RetrievalDiagnostic) => ({
    capability: d.capability,
    provider: d.provider,
    tier: d.tier,
    ok: d.normalizedStatus === "ok",
    category: d.category,
    httpStatus: d.httpStatus,
    latencyMs: d.latencyMs,
    detail: d.detail,
  });

  const rows = checks.map(capability);
  const healthy = rows.length > 0 && rows.every((r) => r.ok);
  return {
    status: "OK",
    healthy,
    checkedAt: new Date().toISOString(),
    // Per-capability rows so a caller can name WHICH capability failed.
    rows,
  };
}

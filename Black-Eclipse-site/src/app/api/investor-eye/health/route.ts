import { NextResponse } from "next/server";
import { recentSourceRuns } from "@/lib/investor-eye/state";
import { listSources } from "@/lib/investor-eye/sources/registry";
import { catalogFor, COMMERCIAL_USE_LABEL, requiredAttributions } from "@/lib/investor-eye/source-catalog";

export const dynamic = "force-dynamic";

// GET /api/investor-eye/health — Data Sources / Data Health (spec §19 / §34).
//
// One row per REGISTERED source, joining:
//   - the live run accounting from the real `SourceRun` log, and
//   - the governance metadata from the source catalog (license, commercial use,
//     attribution, rate limit, freshness).
//
// `hasCatalogEntry` is surfaced explicitly rather than hidden: a source that can
// run but has not declared its license is a compliance gap, and the UI says so
// instead of rendering a blank cell that looks like "no license required".
//
// Honesty: a source that has never run reports no last success rather than a
// fabricated one, and a throttle is its own state — never folded into "error".
export async function GET() {
  try {
    const runs = await recentSourceRuns(60);
    const sources = listSources().map((s) => {
      const sourceRuns = runs.filter((r) => r.source === s.id);
      const last = sourceRuns[0];
      const lastOk = sourceRuns.find((r) => !r.error);
      const totals = sourceRuns.reduce(
        (acc, r) => ({
          received: acc.received + r.recordsReceived,
          accepted: acc.accepted + r.recordsAccepted,
          rejected: acc.rejected + r.recordsRejected,
        }),
        { received: 0, accepted: 0, rejected: 0 },
      );
      const state = last?.status === "rate_limited"
        ? "rate_limited"
        : last?.error
          ? "error"
          : last
            ? "healthy"
            : "idle";
      const catalog = catalogFor(s.id);
      return {
        id: s.id,
        name: s.name,
        capabilities: s.capabilities,
        // Auth: the adapter's `requiresCredentials` is authoritative for whether
        // a key is needed; the catalog records the human-facing policy.
        requiresCredentials: s.requiresCredentials,
        state,
        lastRunAt: last?.finishedAt ?? null,
        lastError: last?.error ?? null,
        lastSuccessAt: lastOk?.finishedAt ?? null,
        latencyMs: last?.durationMs ?? null,
        runCount: sourceRuns.length,
        totals,
        // ── Governance (spec §19 columns: CATEGORY / LICENSE / AUTH) ──────────
        catalog: catalog
          ? {
              provider: catalog.provider,
              category: catalog.category,
              website: catalog.website,
              license: catalog.license,
              licenseUrl: catalog.licenseUrl ?? null,
              termsUrl: catalog.termsUrl ?? null,
              commercialUse: catalog.commercialUse,
              commercialUseLabel: COMMERCIAL_USE_LABEL[catalog.commercialUse],
              requiresApiKey: catalog.requiresApiKey,
              attributionRequired: catalog.attributionRequired,
              attribution: catalog.attribution ?? null,
              rateLimit: catalog.rateLimit ?? null,
              dataFreshness: catalog.dataFreshness,
              note: catalog.note,
            }
          : null,
        hasCatalogEntry: Boolean(catalog),
      };
    });
    return NextResponse.json({
      sources,
      // Centralised credit for every source that requires it, so the UI can
      // render attribution without re-deriving it per row.
      attributions: requiredAttributions(sources.map((s) => s.id)),
      generatedAt: new Date().toISOString(),
    });
  } catch (err) {
    console.error("[api/investor-eye/health] error:", err);
    return NextResponse.json({ sources: [], attributions: [], generatedAt: new Date().toISOString() });
  }
}

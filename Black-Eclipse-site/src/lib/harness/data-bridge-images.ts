// The `image_search` JDdS bridge capability — internet image search.
// Extracted from `data-bridge.ts` to keep the dispatcher small. It returns
// NORMALIZED image results with direct, renderable image URLs and source
// attribution (`src/lib/image-search.ts`). Brave Images is the primary provider
// when configured; Openverse and Wikimedia Commons are keyless fallbacks. A
// genuine empty answer is `no_data`; a failure is `source_failure`; a missing
// credential is reported honestly — never fabricated.

import { searchImages, type ImageSearchType, type SafeSearch } from "@/lib/image-search";
import { describeDiagnostics } from "@/lib/harness/web-provider-resolve";
import type { DataBridgeResult } from "@/lib/harness/data-bridge-types";

export async function imageSearchCapability(params: Record<string, unknown>): Promise<DataBridgeResult> {
  const query = String(params.query ?? "").trim();
  if (!query) {
    return { status: "UNAVAILABLE", failureClass: "invalid_request", error: "query is required" };
  }
  const outcome = await searchImages(query, {
    count: Number(params.count ?? params.limit ?? 8),
    imageType: (params.image_type ?? params.imageType) as ImageSearchType | undefined,
    safeSearch: (params.safe_search ?? params.safeSearch) as SafeSearch | undefined,
    language: typeof params.language === "string" ? params.language : undefined,
    region: typeof params.region === "string" ? params.region : undefined,
    freshness: typeof params.freshness === "string" ? params.freshness : undefined,
  });
  if (outcome.results.length === 0) {
    const configuredFailure = outcome.diagnostics.every(
      (d) => d.normalizedStatus === "failed" && d.category !== "not_configured",
    );
    const missingCredentials = outcome.diagnostics.some((d) => d.category === "not_configured");
    const failureClass = configuredFailure ? "source_failure" : missingCredentials ? "not_configured" : "no_data";
    return {
      status: "UNAVAILABLE",
      failureClass,
      error: configuredFailure
        ? `image providers failed: ${describeDiagnostics(outcome.diagnostics)}`
        : missingCredentials
          ? "no image-search provider is configured; set BRAVE_API_KEY (or rely on the keyless Openverse/Commons fallbacks)"
          : "the image providers returned no results",
      diagnostics: outcome.diagnostics,
    };
  }
  return {
    status: "OK",
    query,
    provider: outcome.provider,
    images: outcome.results,
    results: outcome.results,
    diagnostics: outcome.diagnostics,
  };
}

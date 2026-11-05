import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { fetchCapability } from "@/lib/harness";
import type { DataCapability } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/harness/data — the read-only JDdS bridge used by the Python
// runtime's tools. This is NOT public: the Python service calls it with
// `Authorization: Bearer <CRON_SECRET>` (or from loopback in dev). It performs
// only the whitelisted read capabilities and never writes.

const CAPABILITIES: DataCapability[] = [
  "market_snapshot",
  "fundamentals",
  "financial_statements",
  "sec_filings",
  "news",
  "source_health",
  "research_health",
  "route_probe",
  "coverage",
  "capability_matrix",
  "provider_key_status",
  "live_quote",
  "price_history",
  "crypto_market_data",
  "macro_series",
  "macro_resolve",
  "web_search",
  "web_fetch",
  "web_collect",
  "academic_search",
  "news_search",
  "image_search",
  "video_search",
  "playlist_search",
  "video_metadata",
  "transcript_fetch",
  "course_search",
  "github_search",
  "mcp_secret_resolve",
  "mcp_oauth_token_get",
  "mcp_oauth_token_set",
  "mcp_oauth_token_clear",
  "market_data",
  "market_stream_config",
  "world_events",
  // The model's read-back for eclipse-response blocks: `schema` (exact field
  // names + the live icon vocabulary) and `validate`. Dispatched by
  // `data-bridge.ts` since the read-back shipped; the allowlist entry was
  // missing, so every schema lookup 400'd. Route tests pin it.
  "response_contract",
  // Phase-16 collection routes (dispatched via `data-bridge-extensions.ts`):
  // the SEC filing index, and the operator's declared dataset records.
  "sec_filing_list",
  "custom_dataset_records",
  // The trade-learning loop's read-only journal window (owner-scoped).
  "journal_trades",
];

export async function POST(request: Request) {
  const blocked = guardMutation(request, "harness-data");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });

  try {
    const body = await request.json().catch(() => ({}));
    const capability = (body as Record<string, unknown>).capability;
    if (typeof capability !== "string" || !CAPABILITIES.includes(capability as DataCapability)) {
      return NextResponse.json(
        { status: "UNAVAILABLE", error: `capability must be one of: ${CAPABILITIES.join(", ")}` },
        { status: 400 }
      );
    }
    const params =
      (body as Record<string, unknown>).params &&
      typeof (body as Record<string, unknown>).params === "object"
        ? ((body as Record<string, unknown>).params as Record<string, unknown>)
        : {};

    const result = await fetchCapability(capability as DataCapability, params);
    return NextResponse.json(result);
  } catch (err) {
    console.error("[api/harness/data] POST error:", err);
    // Dev-only diagnostic: a bare "bridge failure" hid the cause of the
    // response_contract 500 (a client React import in the server graph) for a
    // whole debugging round. Production keeps the opaque contract.
    const detail = process.env.NODE_ENV === "development" && err instanceof Error ? `${err.name}: ${err.message}` : undefined;
    // A stable reason CODE lets the agent branch on the failure and degrade to
    // prose/tables instead of guessing block field names. The free-text `detail`
    // (dev only) is diagnostic, never the contract.
    return NextResponse.json(
      { status: "UNAVAILABLE", code: "BRIDGE_ERROR", error: "bridge failure", ...(detail ? { detail } : {}) },
      { status: 500 }
    );
  }
}

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
  "live_quote",
  "price_history",
  "macro_series",
  "macro_resolve",
  "web_search",
  "web_fetch",
  "academic_search",
  "news_search",
  "image_search",
  "video_search",
  "mcp_secret_resolve",
  "mcp_oauth_token_get",
  "mcp_oauth_token_set",
  "mcp_oauth_token_clear",
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
    return NextResponse.json({ status: "UNAVAILABLE", error: "bridge failure" }, { status: 500 });
  }
}

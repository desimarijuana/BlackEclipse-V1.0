import { NextResponse } from "next/server";
import { registerBuiltinConnectors } from "@/lib/connectors";
import { runCapability } from "@/lib/connectors/runtime";
import { loadConnectorsIntoRegistry } from "@/lib/connectors/store";
import type { Capability } from "@/lib/connectors/types";

export const dynamic = "force-dynamic";

const CAPABILITIES: Capability[] = [
  "PRICE",
  "OHLCV",
  "QUOTE",
  "FUNDAMENTALS",
  "NEWS",
  "MACRO",
  "CUSTOM_DATASET",
];

/**
 * GET /api/data/[capability]?symbol=...&connector=...
 *
 * Server-side capability resolution. DataHub (client) calls this route; this
 * route decides which connector serves the capability. Provenance is decided on
 * the server and returned with the payload, so widgets never infer it.
 *
 * The resolver returns real data or UNAVAILABLE — it never fabricates data.
 * Route-level demo fallbacks remain in the routes that already implement them.
 */
export async function GET(
  request: Request,
  context: { params: Promise<{ capability: string }> }
) {
  try {
    const { capability: raw } = await context.params;
    const capability = raw.toUpperCase() as Capability;
    if (!CAPABILITIES.includes(capability)) {
      return NextResponse.json({ error: `Unknown capability: ${raw}` }, { status: 400 });
    }

    const url = new URL(request.url);
    const params: Record<string, string> = {};
    for (const [key, value] of url.searchParams) {
      if (key === "connector") continue;
      params[key] = value;
    }
    const connectorId = url.searchParams.get("connector") ?? undefined;

    registerBuiltinConnectors();
    await loadConnectorsIntoRegistry();

    const result = await runCapability({ capability, params, connectorId });
    return NextResponse.json({
      ok: result.ok,
      capability,
      data: result.data ?? null,
      provenance: result.provenance,
      source: result.source,
      retrievedAt: result.retrievedAt,
      error: result.error ?? null,
    });
  } catch (err) {
    console.error("[api/data] error:", err);
    return NextResponse.json(
      {
        ok: false,
        data: null,
        provenance: "UNAVAILABLE",
        source: "none",
        retrievedAt: new Date().toISOString(),
        error: { code: "network", message: "Capability request failed" },
      },
      { status: 500 }
    );
  }
}

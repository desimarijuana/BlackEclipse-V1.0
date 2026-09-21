import { NextResponse } from "next/server";
import { assembleState } from "@/lib/investor-eye/state";
import {
  buildConflictLayer, buildEnergyLayer, buildTradeLayer, buildWeatherLayer,
  buildFiresLayer, buildShippingLayer, buildCommoditiesLayer,
  buildCountryEventFill, LAYER_META, ALL_LAYER_IDS,
} from "@/lib/investor-eye/layers";
import { checkMutationAllowed, rateLimit, clientKey } from "@/lib/api-guard";

export const dynamic = "force-dynamic";

// GET  /api/investor-eye/layers/:layer — a single layer's data.
// POST /api/investor-eye/layers/:layer — force a rebuild of the source state
//      (guarded + rate-limited; a rebuild hits public sources).
export async function GET(request: Request, { params }: { params: Promise<{ layer: string }> }) {
  const { layer: layerId } = await params;
  const { searchParams } = new URL(request.url);

  if (!ALL_LAYER_IDS.includes(layerId as (typeof ALL_LAYER_IDS)[number])) {
    return NextResponse.json({ error: "unknown_layer", layer: layerId }, { status: 404 });
  }
  const hoursRaw = Number(searchParams.get("hours") ?? "24");
  const hours = Number.isFinite(hoursRaw) && hoursRaw > 0 ? Math.min(hoursRaw, 24 * 30) : 24;

  try {
    const state = await assembleState({ hours });
    const layer = buildLayer(layerId, state);
    if (!layer) {
      return NextResponse.json({
        id: layerId, name: LAYER_META[layerId as keyof typeof LAYER_META]?.name ?? layerId,
        data: [], provenance: "UNAVAILABLE",
        note: "Layer has no data in this window.",
      });
    }
    return NextResponse.json({
      id: layer.id,
      name: layer.name,
      type: layer.type,
      data: layer.data(),
      provenance: state.status.provenance,
    });
  } catch (err) {
    console.error(`[api/investor-eye/layers/${layerId}] error:`, err);
    return NextResponse.json({ id: layerId, data: [], provenance: "UNAVAILABLE" });
  }
}

export async function POST(request: Request, { params }: { params: Promise<{ layer: string }> }) {
  const { layer: layerId } = await params;
  // Rebuilding hits public sources, so treat it as an expensive mutation.
  const guard = checkMutationAllowed(request);
  if (!guard.allowed) {
    return NextResponse.json({ error: guard.reason }, { status: 403 });
  }
  const rl = rateLimit(`investor-eye:refresh:${clientKey(request)}`, { limit: 6, windowMs: 60_000 });
  if (!rl.ok) {
    return NextResponse.json({ error: "rate_limited", retryAfterSec: rl.retryAfterSec }, {
      status: 429, headers: { "Retry-After": String(rl.retryAfterSec) },
    });
  }
  try {
    const hoursRaw = Number(new URL(request.url).searchParams.get("hours") ?? "24");
    const hours = Number.isFinite(hoursRaw) && hoursRaw > 0 ? Math.min(hoursRaw, 24 * 30) : 24;
    const state = await assembleState({ hours, force: true });
    return NextResponse.json({ ok: true, generatedAt: state.generatedAt, provenance: state.status.provenance });
  } catch (err) {
    console.error(`[api/investor-eye/layers/${layerId}] rebuild error:`, err);
    return NextResponse.json({ ok: false, error: "unavailable" }, { status: 200 });
  }
}

function buildLayer(layerId: string, state: Awaited<ReturnType<typeof assembleState>>) {
  switch (layerId) {
    case "conflict":
      return buildConflictLayer(state.events);
    case "energy":
      return buildEnergyLayer(state.events);
    case "trade":
      return buildTradeLayer(state.events, state.countries);
    case "weather":
      return buildWeatherLayer(state.events);
    case "fires":
      return buildFiresLayer(state.events);
    case "shipping":
      return buildShippingLayer(state.events);
    case "commodities":
      return buildCommoditiesLayer(state.events);
    case "risk":
      return buildCountryEventFill(state.countries, "risk", "Event Density", false);
    default:
      // events / markets / economy / companies / portfolio are served from
      // /state (they need inputs beyond the event feed).
      return null;
  }
}

import { NextResponse } from "next/server";
import { queryEvents } from "@/lib/investor-eye/state";
import { buildCountryDetail } from "@/lib/investor-eye/phase2";
import { countryByIso2 } from "@/lib/investor-eye/countries";

export const dynamic = "force-dynamic";

// GET /api/investor-eye/countries/:id — country intelligence.
// `:id` accepts an ISO2 code ('PK') or an ISO2/name ('Pakistan').
// Populated fields only: events, markets (from the assembled state), and real
// economic metrics. Fields with no reliable data are simply absent.
export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { searchParams } = new URL(request.url);
  const hoursRaw = Number(searchParams.get("hours") ?? "168");
  const hours = Number.isFinite(hoursRaw) && hoursRaw > 0 ? Math.min(hoursRaw, 24 * 30) : 168;

  const def = countryByIso2(id) ?? countryByIso2(id.toUpperCase());
  const iso2 = def?.iso2 ?? id.toUpperCase();

  try {
    const events = await queryEvents({ hours, iso2, limit: 200 });
    const detail = await buildCountryDetail(iso2);
    return NextResponse.json({
      country: {
        iso2,
        iso3: def?.iso3,
        name: def?.name ?? iso2,
        region: def?.region,
        lon: def?.lon,
        lat: def?.lat,
        marketId: def?.marketId,
        currency: def?.currency,
      },
      events,
      eventCount: events.length,
      metrics: detail.metrics,
      metricsProvenance: detail.provenance,
      windowHours: hours,
    });
  } catch (err) {
    console.error("[api/investor-eye/countries/:id] error:", err);
    return NextResponse.json({
      country: { iso2, name: def?.name ?? iso2 },
      events: [], eventCount: 0, metrics: [], metricsProvenance: "UNAVAILABLE", windowHours: hours,
    });
  }
}

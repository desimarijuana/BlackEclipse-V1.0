import { NextResponse } from "next/server";
import { buildEconomicLayer, ECONOMIC_METRICS } from "@/lib/investor-eye/phase2";

export const dynamic = "force-dynamic";

// GET /api/investor-eye/economy?metric=inflation
// Real economic values from the free FRED public CSV mirror, per country.
// Countries with no series for the metric are simply absent (never zero-filled).
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const metric = searchParams.get("metric") ?? "inflation";
  try {
    const data = await buildEconomicLayer(metric);
    return NextResponse.json({ ...data, metrics: ECONOMIC_METRICS });
  } catch (err) {
    console.error("[api/investor-eye/economy] error:", err);
    return NextResponse.json({
      metricId: metric, metricLabel: metric, unit: "", values: {},
      provenance: "UNAVAILABLE", metrics: ECONOMIC_METRICS,
    });
  }
}

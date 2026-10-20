import { NextResponse } from "next/server";
import { getEvolutionDrift } from "@/lib/harness/evolution-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const windowValue = Number(params.get("window") ?? 30);
  const baselineValue = Number(params.get("baseline") ?? 100);
  const thresholdValue = Number(params.get("threshold") ?? 0.1);
  const minSamplesValue = Number(params.get("minSamples") ?? 10);
  try {
    const signal = await getEvolutionDrift({
      scope: params.get("scope") ?? undefined,
      window: Number.isFinite(windowValue) ? windowValue : 30,
      baseline: Number.isFinite(baselineValue) ? baselineValue : 100,
      threshold: Number.isFinite(thresholdValue) ? thresholdValue : 0.1,
      minSamples: Number.isFinite(minSamplesValue) ? minSamplesValue : 10,
    });
    return NextResponse.json({ success: true, ...signal });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "drift check failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}

import { NextResponse } from "next/server";
import { getEvolutionDriftHistory } from "@/lib/harness/evolution-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const windowValue = Number(params.get("window") ?? 30);
  const baselineValue = Number(params.get("baseline") ?? 100);
  const thresholdValue = Number(params.get("threshold") ?? 0.1);
  const minSamplesValue = Number(params.get("minSamples") ?? 10);
  const limitValue = Number(params.get("limit") ?? 12);
  const stepValue = params.get("step");
  try {
    const history = await getEvolutionDriftHistory({
      scope: params.get("scope") ?? undefined,
      window: Number.isFinite(windowValue) ? windowValue : 30,
      baseline: Number.isFinite(baselineValue) ? baselineValue : 100,
      threshold: Number.isFinite(thresholdValue) ? thresholdValue : 0.1,
      minSamples: Number.isFinite(minSamplesValue) ? minSamplesValue : 10,
      limit: Number.isFinite(limitValue) ? limitValue : 12,
      step: stepValue != null && Number.isFinite(Number(stepValue))
        ? Number(stepValue)
        : undefined,
    });
    return NextResponse.json({ success: true, ...history });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "drift history failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}

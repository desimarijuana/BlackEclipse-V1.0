import { NextResponse } from "next/server";
import { createEvolutionDriftCandidate } from "@/lib/harness/clients/evolution-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const params = new URL(request.url).searchParams;
  const windowValue = Number(params.get("window") ?? 30);
  const baselineValue = Number(params.get("baseline") ?? 100);
  const thresholdValue = Number(params.get("threshold") ?? 0.1);
  const minSamplesValue = Number(params.get("minSamples") ?? 10);
  try {
    const result = await createEvolutionDriftCandidate({
      scope: params.get("scope") ?? undefined,
      window: Number.isFinite(windowValue) ? windowValue : 30,
      baseline: Number.isFinite(baselineValue) ? baselineValue : 100,
      threshold: Number.isFinite(thresholdValue) ? thresholdValue : 0.1,
      minSamples: Number.isFinite(minSamplesValue) ? minSamplesValue : 10,
    });
    return NextResponse.json({ success: true, ...result });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "drift candidate creation failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}

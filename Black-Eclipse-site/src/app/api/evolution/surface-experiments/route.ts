import { NextResponse } from "next/server";
import { createEvolutionSurfaceExperiment } from "@/lib/harness/clients/evolution-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";
import type { EvolutionSurfaceExperimentInput } from "@/lib/harness/clients/evolution-client";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as EvolutionSurfaceExperimentInput;
    const result = await createEvolutionSurfaceExperiment(body);
    return NextResponse.json(result);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "surface experiment failed" },
      { status: unavailable ? 503 : 400 },
    );
  }
}

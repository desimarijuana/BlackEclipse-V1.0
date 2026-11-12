import { NextResponse } from "next/server";
import { createEvolutionModelExperiment } from "@/lib/harness/clients/evolution-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const result = await createEvolutionModelExperiment(body);
    return NextResponse.json(result);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "model experiment failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}

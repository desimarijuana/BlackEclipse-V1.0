import { NextResponse } from "next/server";
import { tickEvolutionRsl } from "@/lib/harness/clients/evolution-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

export async function POST() {
  try {
    const result = await tickEvolutionRsl();
    return NextResponse.json(result);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "RSL tick failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}

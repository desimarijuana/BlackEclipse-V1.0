import { NextResponse } from "next/server";
import { listEvolutionCandidates } from "@/lib/harness/clients/evolution-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const candidates = await listEvolutionCandidates();
    return NextResponse.json({ success: true, candidates });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "candidate list failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}

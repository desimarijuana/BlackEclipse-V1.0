import { NextResponse } from "next/server";
import { proposeEvolutionCandidate } from "@/lib/harness/evolution-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";
import type { EvolutionProposeInput } from "@/lib/harness/evolution-client";

export const dynamic = "force-dynamic";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  try {
    const body = (await request.json()) as EvolutionProposeInput;
    const result = await proposeEvolutionCandidate(id, body);
    return NextResponse.json(result);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "candidate proposal failed" },
      { status: unavailable ? 503 : 400 },
    );
  }
}

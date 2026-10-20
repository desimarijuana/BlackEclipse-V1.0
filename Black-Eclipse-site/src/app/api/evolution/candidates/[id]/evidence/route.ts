import { NextResponse } from "next/server";
import { evolutionCandidateEvidence } from "@/lib/harness/evolution-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try {
    const evidence = await evolutionCandidateEvidence(id);
    return NextResponse.json({ success: true, ...evidence });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "evidence not found" },
      { status: unavailable ? 503 : 404 },
    );
  }
}

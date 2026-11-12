import { NextResponse } from "next/server";
import { getEvolutionCandidateState } from "@/lib/harness/clients/evolution-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const scope = new URL(request.url).searchParams.get("scope") ?? undefined;
  try {
    const result = await getEvolutionCandidateState(id, scope);
    return NextResponse.json({ success: true, ...result });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "candidate state lookup failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}

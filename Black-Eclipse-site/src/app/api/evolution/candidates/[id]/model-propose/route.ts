import { NextResponse } from "next/server";
import { modelProposeEvolutionCandidate } from "@/lib/harness/clients/evolution-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const k = Number(new URL(request.url).searchParams.get("k") ?? "");
  try {
    const result = await modelProposeEvolutionCandidate(
      id, Number.isFinite(k) && k > 0 ? k : undefined,
    );
    return NextResponse.json({ success: true, ...result });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "model proposal failed" },
      { status: unavailable ? 503 : 400 },
    );
  }
}

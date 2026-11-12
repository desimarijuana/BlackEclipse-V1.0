import { NextResponse } from "next/server";
import { getEvolutionCandidate, listEvolutionAttempts } from "@/lib/harness/clients/evolution-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try {
    const [candidate, attempts] = await Promise.all([
      getEvolutionCandidate(id),
      listEvolutionAttempts(id),
    ]);
    return NextResponse.json({ success: true, candidate, attempts });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "candidate not found" },
      { status: unavailable ? 503 : 404 },
    );
  }
}

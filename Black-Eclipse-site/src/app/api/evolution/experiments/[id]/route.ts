import { NextResponse } from "next/server";
import { getEvolutionExperiment } from "@/lib/harness/clients/evolution-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try {
    const detail = await getEvolutionExperiment(id);
    return NextResponse.json({ success: true, ...detail });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "experiment not found" },
      { status: unavailable ? 503 : 404 },
    );
  }
}

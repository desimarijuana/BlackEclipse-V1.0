import { NextResponse } from "next/server";
import { rollbackEvolutionSurfaceActivation } from "@/lib/harness/clients/evolution-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

export async function POST(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  try {
    const result = await rollbackEvolutionSurfaceActivation(id);
    return NextResponse.json({ success: true, ...result });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "surface rollback failed" },
      { status: unavailable ? 503 : 400 },
    );
  }
}

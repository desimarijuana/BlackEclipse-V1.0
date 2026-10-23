import { NextResponse } from "next/server";
import { applyEvolutionAutonomy } from "@/lib/harness/evolution-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

export async function POST(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  try {
    const result = await applyEvolutionAutonomy(id);
    return NextResponse.json(result);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "autonomy apply failed" },
      { status: unavailable ? 503 : 400 },
    );
  }
}

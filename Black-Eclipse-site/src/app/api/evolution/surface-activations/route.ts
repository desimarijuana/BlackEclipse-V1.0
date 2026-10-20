import { NextResponse } from "next/server";
import { listEvolutionSurfaceActivations } from "@/lib/harness/evolution-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const limit = Number(new URL(request.url).searchParams.get("limit") ?? 50);
  try {
    const result = await listEvolutionSurfaceActivations(
      Number.isFinite(limit) ? Math.max(1, Math.min(200, limit)) : 50,
    );
    return NextResponse.json({ success: true, ...result });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "activation list failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}

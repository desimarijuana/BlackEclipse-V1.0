import { NextResponse } from "next/server";
import { pauseEvolutionAutonomy } from "@/lib/harness/clients/evolution-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  try {
    const body = (await request.json().catch(() => ({}))) as { reason?: string };
    const result = await pauseEvolutionAutonomy(
      typeof body.reason === "string" ? body.reason : "",
    );
    return NextResponse.json(result);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "pause autonomy failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}

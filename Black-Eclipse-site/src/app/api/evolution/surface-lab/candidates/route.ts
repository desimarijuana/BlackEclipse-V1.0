import { NextResponse } from "next/server";
import { listEvolutionSurfaceLabCandidatesBrowser } from "@/lib/harness/evolution-browser";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const limitValue = Number(params.get("limit") ?? 10);
  try {
    const result = await listEvolutionSurfaceLabCandidatesBrowser({
      limit: Number.isFinite(limitValue) ? limitValue : 10,
    });
    return NextResponse.json({ ...result, success: true });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "surface lab candidates failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}

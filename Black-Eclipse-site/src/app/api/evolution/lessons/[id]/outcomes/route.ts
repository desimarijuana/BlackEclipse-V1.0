import { NextResponse } from "next/server";
import { getEvolutionLessonOutcomes } from "@/lib/harness/evolution-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const limit = Number(new URL(request.url).searchParams.get("limit") ?? 50);
  try {
    const result = await getEvolutionLessonOutcomes(
      id,
      Number.isFinite(limit) ? Math.max(1, Math.min(200, limit)) : 50,
    );
    return NextResponse.json({ success: true, ...result });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "lesson outcomes failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}

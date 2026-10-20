import { NextResponse } from "next/server";
import { listEvolutionLessons } from "@/lib/harness/evolution-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const limit = Number(new URL(request.url).searchParams.get("limit") ?? 50);
  try {
    const lessons = await listEvolutionLessons(
      Number.isFinite(limit) ? Math.max(1, Math.min(200, limit)) : 50,
    );
    return NextResponse.json({ success: true, lessons });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "lesson list failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}

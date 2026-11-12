import { NextResponse } from "next/server";
import { adoptEvolutionLesson } from "@/lib/harness/clients/evolution-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";
import type { EvolutionLessonInput } from "@/lib/harness/clients/evolution-client";

export const dynamic = "force-dynamic";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  try {
    const input = (await request.json()) as EvolutionLessonInput;
    const result = await adoptEvolutionLesson(id, input);
    return NextResponse.json({ success: true, ...result });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "lesson adoption failed" },
      { status: unavailable ? 503 : 400 },
    );
  }
}

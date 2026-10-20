import { NextResponse } from "next/server";
import { activateEvolutionSurfaceState } from "@/lib/harness/evolution-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  try {
    const body = (await request.json().catch(() => ({}))) as { scope?: string };
    const result = await activateEvolutionSurfaceState(id, body.scope);
    return NextResponse.json({ success: true, ...result });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "surface activation failed" },
      { status: unavailable ? 503 : 400 },
    );
  }
}

import { NextResponse } from "next/server";
import { queueEvolutionSurfaceLabCandidateBrowser } from "@/lib/harness/clients/evolution-browser";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

export async function POST(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  if (!id) {
    return NextResponse.json({ error: "id is required" }, { status: 400 });
  }
  try {
    const result = await queueEvolutionSurfaceLabCandidateBrowser(id);
    return NextResponse.json({ ...result, success: true });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "queueing the candidate failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}

import { NextResponse } from "next/server";
import { postLandingProbe } from "@/lib/harness/clients/code-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

export async function POST(request: Request, { params }: { params: Promise<{ rollbackId: string }> }) {
  const { rollbackId } = await params;
  const body = (await request.json().catch(() => ({}))) as {
    runId?: string;
    activationId?: string;
    alreadyRestarted?: boolean;
  };
  if (!rollbackId || !body.runId) {
    return NextResponse.json({ error: "rollbackId and runId are required" }, { status: 400 });
  }
  try {
    const postLanding = await postLandingProbe(
      rollbackId,
      body.runId,
      body.alreadyRestarted ?? true,
      body.activationId,
    );
    return NextResponse.json({ success: true, postLanding });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "post-landing probe failed" },
      { status: unavailable ? 503 : 409 },
    );
  }
}

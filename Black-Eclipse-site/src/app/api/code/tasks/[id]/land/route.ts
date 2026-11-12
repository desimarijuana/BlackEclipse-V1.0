import { NextResponse } from "next/server";
import { getLandPlan } from "@/lib/harness/clients/code-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try {
    const plan = await getLandPlan(id);
    return NextResponse.json({ success: true, plan });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "could not load the checks" },
      { status: unavailable ? 503 : 400 },
    );
  }
}

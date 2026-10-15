import { NextResponse } from "next/server";
import { rollbackPromotion } from "@/lib/harness/code-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

export async function POST(_request: Request, { params }: { params: Promise<{ rollbackId: string }> }) {
  const { rollbackId } = await params;
  if (!rollbackId) {
    return NextResponse.json({ error: "rollbackId is required" }, { status: 400 });
  }
  try {
    const rollback = await rollbackPromotion(rollbackId);
    return NextResponse.json({ success: true, rollback });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "rollback failed" },
      { status: unavailable ? 503 : 409 },
    );
  }
}

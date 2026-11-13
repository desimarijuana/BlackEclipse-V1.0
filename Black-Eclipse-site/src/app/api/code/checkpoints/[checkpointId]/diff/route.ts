import { NextResponse } from "next/server";
import { diffFileCheckpoint } from "@/lib/harness/clients/code-client";

export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ checkpointId: string }> },
) {
  const { checkpointId } = await params;
  try {
    return NextResponse.json({ success: true, ...(await diffFileCheckpoint(checkpointId)) });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "checkpoint diff failed" },
      { status: 500 },
    );
  }
}

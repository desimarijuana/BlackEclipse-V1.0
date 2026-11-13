import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { restoreFileCheckpoint } from "@/lib/harness/clients/code-client";

export const dynamic = "force-dynamic";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ checkpointId: string }> },
) {
  const blocked = guardMutation(request, "code-checkpoint-restore");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const { checkpointId } = await params;
  const body = (await request.json().catch(() => ({}))) as {
    paths?: string[];
    all?: boolean;
  };
  try {
    return NextResponse.json({
      success: true,
      ...(await restoreFileCheckpoint(checkpointId, body)),
    });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "restore failed" },
      { status: 500 },
    );
  }
}

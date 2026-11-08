import { NextResponse } from "next/server";
import { getCodeTaskWithSession } from "@/lib/harness/code-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try {
    const { task, session } = await getCodeTaskWithSession(id);
    return NextResponse.json({ success: true, task, session });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "task not found" },
      { status: unavailable ? 503 : 404 },
    );
  }
}

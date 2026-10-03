import { NextResponse } from "next/server";
import { revokeTrustedRoot } from "@/lib/harness/code-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// DELETE /api/workspace/roots/[id] — revoke an approved folder.
export async function DELETE(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params;
    await revokeTrustedRoot(id);
    return NextResponse.json({ success: true, revoked: id });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "revoke failed" },
      { status: unavailable ? 503 : 400 },
    );
  }
}

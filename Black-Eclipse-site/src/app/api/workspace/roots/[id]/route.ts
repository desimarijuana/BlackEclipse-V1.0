import { NextResponse } from "next/server";
import { requireApiAuth } from "@/lib/auth/server";
import { revokeTrustedRoot } from "@/lib/harness/clients/code-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// DELETE /api/workspace/roots/[id] — revoke an approved folder.
export async function DELETE(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const denied = await requireApiAuth(request);
  if (denied) return denied;
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

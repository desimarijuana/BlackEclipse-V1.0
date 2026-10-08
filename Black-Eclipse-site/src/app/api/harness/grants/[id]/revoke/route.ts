import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { revokeStandingGrant } from "@/lib/harness/grants-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/harness/grants/:id/revoke — revoke an "always allow" permission.
export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardMutation(request, "grant-revoke");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const { id } = await params;
    const revoked = await revokeStandingGrant(id);
    return NextResponse.json({ success: true, revoked });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    const notFound = err instanceof Error && /404/.test(err.message);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Grant revoke failed" },
      { status: unavailable ? 503 : notFound ? 404 : 400 }
    );
  }
}

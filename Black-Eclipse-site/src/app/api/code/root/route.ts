import { NextResponse } from "next/server";
import { getCodeRoot } from "@/lib/harness/clients/code-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/code/root — the runtime's server-resolved code root. Read-only. The
// task list's schedule action uses it so a code job has the folder it needs; the
// value can never point a run elsewhere (the runtime confirms it).
export async function GET() {
  try {
    const root = await getCodeRoot();
    return NextResponse.json({ success: true, root, available: root != null });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "root lookup failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}

import { NextResponse } from "next/server";
import { requireApiAuth } from "@/lib/auth/server";
import { restartPythonRuntime } from "@/lib/harness/python-runtime";

export const dynamic = "force-dynamic";

/**
 * Restart the managed Python agent runtime (the self-hosting seam, Track B).
 * A change under `python/harness/**` only takes effect after a restart; the
 * runtime cannot restart itself, so the front door owns it.
 */
export async function POST(request: Request) {
  const denied = await requireApiAuth(request);
  if (denied) return denied;
  try {
    const ok = await restartPythonRuntime();
    return NextResponse.json({ success: ok, healthy: ok });
  } catch (err) {
    return NextResponse.json(
      { success: false, healthy: false, error: err instanceof Error ? err.message : "restart failed" },
      { status: 503 },
    );
  }
}

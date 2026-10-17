import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { createMonitor, listMonitors } from "@/lib/harness/automation-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    return NextResponse.json({ success: true, monitors: await listMonitors() });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "monitor list failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}

export async function POST(request: Request) {
  const blocked = guardMutation(request, "monitor-create");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = (await request.json().catch(() => ({}))) as {
      monitorId?: string;
      params?: Record<string, string | number>;
      name?: string;
    };
    if (!body.monitorId) {
      return NextResponse.json({ error: "`monitorId` is required" }, { status: 400 });
    }
    const automation = await createMonitor({
      monitorId: body.monitorId,
      params: body.params ?? {},
      name: body.name,
    });
    return NextResponse.json({ success: true, automation });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "monitor create failed" },
      { status: 400 },
    );
  }
}

import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import {
  cancelLoop,
  pauseLoop,
  resumeLoop,
} from "@/lib/harness/clients/autonomy-client";

export const dynamic = "force-dynamic";

const ACTIONS = new Set(["pause", "resume", "cancel"]);

export async function POST(request: Request, context: { params: Promise<{ id: string; action: string }> }) {
  const { id, action } = await context.params;
  if (!ACTIONS.has(action)) {
    return NextResponse.json({ error: "unknown action" }, { status: 404 });
  }
  const blocked = guardMutation(request, `loop-${action}`);
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = (await request.json().catch(() => ({}))) as { reason?: string };
    const loop =
      action === "pause"
        ? await pauseLoop(id, typeof body.reason === "string" ? body.reason : "")
        : action === "resume"
          ? await resumeLoop(id)
          : await cancelLoop(id);
    return NextResponse.json({ success: true, loop });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "loop action failed" },
      { status: 400 },
    );
  }
}

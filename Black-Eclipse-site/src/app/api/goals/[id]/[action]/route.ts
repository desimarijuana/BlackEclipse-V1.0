import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import {
  cancelGoal,
  extendGoal,
  goalVerdicts,
  pauseGoal,
  reevaluateGoal,
  resumeGoal,
} from "@/lib/harness/clients/autonomy-client";

export const dynamic = "force-dynamic";

const POST_ACTIONS = new Set(["pause", "resume", "cancel", "extend", "reevaluate"]);

export async function GET(_request: Request, context: { params: Promise<{ id: string; action: string }> }) {
  const { id, action } = await context.params;
  if (action !== "verdicts") {
    return NextResponse.json({ error: "unknown action" }, { status: 404 });
  }
  try {
    const verdicts = await goalVerdicts(id);
    return NextResponse.json({ success: true, verdicts, goalId: id });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "verdict read failed" },
      { status: 404 },
    );
  }
}

export async function POST(request: Request, context: { params: Promise<{ id: string; action: string }> }) {
  const { id, action } = await context.params;
  if (!POST_ACTIONS.has(action)) {
    return NextResponse.json({ error: "unknown action" }, { status: 404 });
  }
  const blocked = guardMutation(request, `goal-${action}`);
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = (await request.json().catch(() => ({}))) as { reason?: string; turns?: number };
    const goal =
      action === "pause"
        ? await pauseGoal(id, typeof body.reason === "string" ? body.reason : "")
        : action === "resume"
          ? await resumeGoal(id)
          : action === "extend"
            ? await extendGoal(id, typeof body.turns === "number" ? body.turns : 5)
            : action === "reevaluate"
              ? await reevaluateGoal(id)
              : await cancelGoal(id);
    return NextResponse.json({ success: true, goal });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "goal action failed" },
      { status: 400 },
    );
  }
}

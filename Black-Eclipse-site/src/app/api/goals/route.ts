import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import {
  createGoal,
  listGoals,
  type CreateGoalInput,
} from "@/lib/harness/clients/autonomy-client";
import { resolveRunModelSettings } from "@/lib/harness/run-service";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

const AUTONOMY = ["plan_only", "edit_verify", "approve_external"] as const;
const TASK_TYPES = ["code", "research", "document", "workflow", "finance", "data", "general"] as const;

export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const goals = await listGoals({
      sessionId: url.searchParams.get("sessionId") ?? undefined,
      status: url.searchParams.get("status") ?? undefined,
    });
    return NextResponse.json({ success: true, goals });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "goal list failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}

export async function POST(request: Request) {
  const blocked = guardMutation(request, "goal-create");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = (await request.json().catch(() => ({}))) as Partial<CreateGoalInput> & {
      modelSettings?: Record<string, unknown>;
    };
    const objective = typeof body.objective === "string" ? body.objective.trim() : "";
    if (!objective) {
      return NextResponse.json({ error: "objective is required" }, { status: 400 });
    }
    if (body.autonomy !== undefined && !(AUTONOMY as readonly string[]).includes(body.autonomy)) {
      return NextResponse.json({ error: "unknown autonomy" }, { status: 400 });
    }
    if (body.taskType !== undefined && !(TASK_TYPES as readonly string[]).includes(body.taskType)) {
      return NextResponse.json({ error: "unknown task type" }, { status: 400 });
    }
    const model =
      body.model && (body.model.provider || body.model.model)
        ? body.model
        : await resolveRunModelSettings(undefined);
    const input: CreateGoalInput = {
      objective,
      acceptance: Array.isArray(body.acceptance) ? body.acceptance.filter((v) => typeof v === "string").slice(0, 24) : [],
      constraints: Array.isArray(body.constraints) ? body.constraints.filter((v) => typeof v === "string").slice(0, 24) : [],
      deliverables: Array.isArray(body.deliverables) ? body.deliverables.filter((v) => typeof v === "string").slice(0, 24) : [],
      boundaries: Array.isArray(body.boundaries) ? body.boundaries.filter((v) => typeof v === "string").slice(0, 24) : [],
      stopWhen: Array.isArray(body.stopWhen) ? body.stopWhen.filter((v) => typeof v === "string").slice(0, 24) : [],
      gates: Array.isArray(body.gates) ? body.gates.slice(0, 24) : [],
      maxTurns: typeof body.maxTurns === "number" ? body.maxTurns : undefined,
      sessionId: typeof body.sessionId === "string" ? body.sessionId : undefined,
      workspaceId: typeof body.workspaceId === "string" ? body.workspaceId : undefined,
      autonomy: body.autonomy,
      taskType: body.taskType,
      model: { provider: model.provider, model: model.model, baseUrl: model.baseUrl },
      start: body.start !== false,
      allowParallel: body.allowParallel === true,
    };
    const goal = await createGoal(input);
    return NextResponse.json({ success: true, goal });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    const message = err instanceof Error ? err.message : "goal create failed";
    // Preserve the engine's 409 semantics for the two typed refusals the chat
    // command reacts to, instead of flattening them to 400.
    const conflict = /goal loop is off|already has an active goal/i.test(message);
    return NextResponse.json(
      { error: message },
      { status: unavailable ? 503 : conflict ? 409 : 400 },
    );
  }
}

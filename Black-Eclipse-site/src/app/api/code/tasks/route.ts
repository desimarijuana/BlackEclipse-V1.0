import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { listCodeTasks, createCodeTask, type Autonomy } from "@/lib/harness/code-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

const AUTONOMY: Autonomy[] = ["plan_only", "edit_verify", "approve_external"];

export async function GET() {
  try {
    const tasks = await listCodeTasks();
    return NextResponse.json({ success: true, tasks });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "task list failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}

export async function POST(request: Request) {
  const blocked = guardMutation(request, "code-task-create");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = (await request.json().catch(() => ({}))) as {
      query?: string;
      autonomy?: string;
      workspaceId?: string;
      modelSettings?: Record<string, unknown>;
      callbackBaseUrl?: string;
    };
    if (typeof body.query !== "string" || !body.query.trim()) {
      return NextResponse.json({ error: "query is required" }, { status: 400 });
    }
    const autonomy = (body.autonomy ?? "plan_only") as Autonomy;
    if (!AUTONOMY.includes(autonomy)) {
      return NextResponse.json({ error: "unknown autonomy" }, { status: 400 });
    }
    const task = await createCodeTask({
      query: body.query.trim(),
      autonomy,
      workspaceId: body.workspaceId,
      modelSettings: body.modelSettings ?? {},
      callbackBaseUrl: body.callbackBaseUrl,
    });
    return NextResponse.json({ success: true, task });
  } catch (err) {
    return NextResponse.json({ error: err instanceof Error ? err.message : "task create failed" }, { status: 500 });
  }
}

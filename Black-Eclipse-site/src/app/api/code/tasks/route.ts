import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { listCodeTasks, createCodeTask, type Autonomy } from "@/lib/harness/code-client";
import { resolveRunModelSettings } from "@/lib/harness/run-service";
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
    // A UI "Build this" action has no vault access, so the model settings are
    // resolved server-side (the same one resolution path a chat run uses). The
    // runtime binds its own server-resolved code root; no workspace ref is sent.
    const modelSettings =
      body.modelSettings && Object.keys(body.modelSettings).length
        ? body.modelSettings
        : await resolveRunModelSettings();
    const task = await createCodeTask({
      query: body.query.trim(),
      autonomy,
      workspaceId: body.workspaceId,
      modelSettings,
      callbackBaseUrl: body.callbackBaseUrl,
    });
    return NextResponse.json({ success: true, task });
  } catch (err) {
    return NextResponse.json({ error: err instanceof Error ? err.message : "task create failed" }, { status: 500 });
  }
}

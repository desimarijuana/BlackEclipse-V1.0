import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { runWorkflow } from "@/lib/harness/clients/workflows-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";
import { getLLMConfig } from "@/lib/settings";
import { runtimeBaseUrl, runtimeCallbackToken } from "@/lib/harness/runtime-auth";

export const dynamic = "force-dynamic";
export const maxDuration = 300;

// POST /api/harness/workflows/run — execute a saved workflow over the EXISTING
// Python graph. The workflow path is flag-gated in the runtime and DEFAULT OFF;
// when disabled the runtime returns an explicit `disabled` status (never a fake
// run). Model settings are resolved here from the vault, exactly as for a chat
// run — the runtime never reads the vault.
export async function POST(request: Request) {
  const blocked = guardMutation(request, "workflows-run");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const workflowId = typeof body.workflowId === "string" ? body.workflowId : "";
    if (!workflowId) return NextResponse.json({ error: "workflowId is required" }, { status: 400 });

    const llm = await getLLMConfig();
    if (!llm) {
      return NextResponse.json({ error: "No model provider is configured" }, { status: 400 });
    }
    const result = await runWorkflow({
      workflowId,
      runId: typeof body.runId === "string" ? body.runId : `wf_${Date.now()}`,
      input: (body.input as Record<string, unknown>) ?? {},
      agentId: body.agentId,
      userId: body.userId,
      sessionId: body.sessionId,
      profileId: body.profileId,
      projectId: body.projectId,
      callbackBaseUrl: runtimeBaseUrl(),
      callbackToken: runtimeCallbackToken(),
      modelSettings: {
        provider: llm.provider,
        baseUrl: llm.baseUrl,
        apiKey: llm.apiKey,
        model: llm.model,
        contextWindow: llm.contextWindow,
      },
    });
    return NextResponse.json({ success: true, ...result });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "workflow run failed" },
      { status: unavailable ? 503 : 400 },
    );
  }
}

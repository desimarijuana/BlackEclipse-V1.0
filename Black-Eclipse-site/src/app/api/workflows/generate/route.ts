// ── /api/workflows/generate — create a SAVED workflow from a sentence ────────
// The chat tool `create_workflow` cannot write JDDS itself: the workflow catalog
// lives in Prisma and only the front door owns it. This route is the one call
// that closes the loop — it resolves the model credentials from the settings
// vault (in memory only), asks the Python planner for a validated IR, and writes
// it through the SAME store the gallery uses. A plan that does not validate is
// rejected; nothing is saved.

import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";
import { runtimeIdentityHeaders } from "@/lib/harness/runtime-identity";
import { getLLMConfig } from "@/lib/settings";
import { createWorkflow } from "@/lib/graph-studio/server-store";
import { readWorkflowIR } from "@/lib/graph-studio/migrations";

export const dynamic = "force-dynamic";

/** The planner's answer; only `ok` + `ir` matter to this route. */
interface PlanResult {
  ok?: boolean;
  ir?: unknown;
  errors?: Array<{ message?: string }>;
  warnings?: string[];
  nodeCount?: number;
  edgeCount?: number;
  executionMode?: string;
}

function planFailure(plan: PlanResult): string {
  const messages = (plan.errors ?? [])
    .map((item) => (typeof item?.message === "string" ? item.message : ""))
    .filter(Boolean);
  return messages.join("; ") || "The model did not return a usable workflow.";
}

export async function POST(request: Request) {
  const blocked = guardMutation(request, "workflows-generate");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const healthy = await ensurePythonRuntime();
  if (!healthy) {
    return NextResponse.json({ error: "The Python agent runtime is not available." }, { status: 503 });
  }

  const body = (await request.json().catch(() => ({}))) as {
    objective?: unknown;
    name?: unknown;
  };
  const objective = typeof body.objective === "string" ? body.objective.trim() : "";
  if (objective.length < 8) {
    return NextResponse.json(
      { error: "Describe the workflow you want in a sentence (at least a few words)." },
      { status: 400 },
    );
  }
  if (objective.length > 4_000) {
    return NextResponse.json({ error: "That description is too long." }, { status: 400 });
  }

  const llm = await getLLMConfig();
  if (!llm || llm.provider === "mock") {
    return NextResponse.json(
      { error: "Creating a workflow needs a configured model provider. Configure one in Settings." },
      { status: 400 },
    );
  }
  const modelSettings = {
    provider: llm.provider,
    baseUrl: llm.baseUrl,
    apiKey: llm.apiKey,
    model: llm.model,
    contextWindow: llm.contextWindow,
  };

  const token = runtimeCallbackToken();
  let plan: PlanResult;
  try {
    const res = await fetch(`${HARNESS_PY_URL}/graphs/plan`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { "X-Harness-Operator": token } : {}),
        ...(await runtimeIdentityHeaders(request)),
      },
      body: JSON.stringify({ objective, modelSettings }),
      // Keep this under the Python tool's 120 s ceiling so the caller always
      // learns the outcome instead of timing out after the workflow is written.
      signal: AbortSignal.timeout(110_000),
    });
    const data = (await res.json().catch(() => ({}))) as PlanResult & {
      error?: string;
      detail?: unknown;
    };
    if (!res.ok) {
      const detail =
        typeof data.detail === "string"
          ? data.detail
          : typeof data.error === "string"
            ? data.error
            : `Graph planning failed (${res.status}).`;
      return NextResponse.json({ error: detail }, { status: res.status });
    }
    plan = data;
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Graph planning failed" },
      { status: 502 },
    );
  }

  if (!plan.ok || !plan.ir) {
    return NextResponse.json(
      {
        error: planFailure(plan),
        errors: plan.errors ?? [],
        warnings: plan.warnings ?? [],
      },
      { status: 422 },
    );
  }

  try {
    const ir = readWorkflowIR(plan.ir);
    const requestedName = typeof body.name === "string" ? body.name.trim().slice(0, 120) : "";
    const name = requestedName || ir.name || "Generated workflow";
    // The row name and the document name must agree: a later save adopts `ir.name`.
    ir.name = name;
    const workflow = await createWorkflow({
      name,
      description: ir.description || `Generated from: ${objective}`,
      tags: ["generated"],
      ir,
    });
    return NextResponse.json(
      {
        workflow: {
          id: workflow.id,
          name: workflow.name,
          description: workflow.description,
          currentVersion: workflow.currentVersion,
        },
        plan: {
          nodeCount: plan.nodeCount ?? ir.nodes.length,
          edgeCount: plan.edgeCount ?? ir.edges.length,
          executionMode: plan.executionMode ?? ir.settings.executionMode,
          warnings: plan.warnings ?? [],
        },
      },
      { status: 201 },
    );
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to save the workflow" },
      { status: 400 },
    );
  }
}

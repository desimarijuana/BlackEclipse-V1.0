// ── /api/graph-runs/node-test — execute ONE node ─────────────────────────────
// The editor's "Test node" action. Unlike /runs, this does NOT load a persisted
// workflow: the node type, config and inputs come from the (possibly unsaved)
// editor. The Python runtime therefore re-validates everything and runs the
// executor in its safe envelope (only none/read side effects; write, trading,
// network and model nodes are refused), with the node's own hard timeout.
// Nothing is persisted.

import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";
import { runtimeIdentityHeaders } from "@/lib/harness/runtime-identity";
import { validateBoundedJson } from "@/lib/graph-studio/run-input";

export const dynamic = "force-dynamic";

const MODES = new Set(["research", "backtest", "paper", "live"]);

export async function POST(request: Request) {
  const blocked = guardMutation(request, "graph-node-test");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });

  const healthy = await ensurePythonRuntime();
  if (!healthy) {
    return NextResponse.json(
      { error: "The Python agent runtime is not available. Install the runtime: npm run setup:python" },
      { status: 503 },
    );
  }

  const body = (await request.json().catch(() => ({}))) as {
    nodeType?: unknown;
    version?: unknown;
    config?: unknown;
    inputs?: unknown;
    mode?: unknown;
  };

  const nodeType = typeof body.nodeType === "string" ? body.nodeType.trim() : "";
  if (!nodeType || nodeType.length > 200) {
    return NextResponse.json({ error: "nodeType is required." }, { status: 400 });
  }
  const version = typeof body.version === "string" && body.version.trim() ? body.version.trim() : undefined;
  const mode = typeof body.mode === "string" && MODES.has(body.mode) ? body.mode : "research";

  const config = validateBoundedJson(body.config ?? {}, "config");
  if (!config.ok) return NextResponse.json({ error: config.error }, { status: 400 });
  if (!config.value || typeof config.value !== "object" || Array.isArray(config.value)) {
    return NextResponse.json({ error: "config must be a JSON object." }, { status: 400 });
  }

  const inputs = validateBoundedJson(body.inputs ?? {}, "inputs");
  if (!inputs.ok) return NextResponse.json({ error: inputs.error }, { status: 400 });
  if (!inputs.value || typeof inputs.value !== "object" || Array.isArray(inputs.value)) {
    return NextResponse.json({ error: "inputs must be a JSON object keyed by port id." }, { status: 400 });
  }

  const token = runtimeCallbackToken();
  const user = request.headers.get("x-eclipse-user");
  try {
    const res = await fetch(`${HARNESS_PY_URL}/graphs/nodes/test`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { "X-Harness-Operator": token } : {}),
        ...(await runtimeIdentityHeaders(request)),
        ...(user ? { "X-Harness-User": user } : {}),
      },
      signal: AbortSignal.timeout(60_000),
      body: JSON.stringify({
        nodeType,
        version,
        config: config.value,
        inputs: inputs.value,
        mode,
      }),
    });
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "failed to test the node" },
      { status: 502 },
    );
  }
}

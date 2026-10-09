import { NextResponse } from "next/server";
import { guardExpensiveMutation } from "@/lib/api-guard";
import {
  startRun,
  validateRunInput,
  listRunsFromRuntime,
  HarnessError,
  HarnessRuntimeUnavailable,
  toHarnessErrorJson,
} from "@/lib/harness";
import { runtimeIdentityHeaders } from "@/lib/harness/runtime-identity";

export const dynamic = "force-dynamic";
export const maxDuration = 180;

// POST /api/harness/runs — front door to the Python agent runtime.
// The Next.js side validates input + resolves the model/model config; agents,
// tools, events and run persistence live in python/harness/.
export async function POST(request: Request) {
  const blocked = guardExpensiveMutation(request, "harness-run", { limit: 12, windowMs: 5 * 60_000 });
  if (blocked) {
    return NextResponse.json(blocked.body, { status: blocked.status, headers: blocked.headers });
  }
  try {
    const body = await request.json().catch(() => ({}));
    const validated = validateRunInput(body);
    if (!validated.ok || !validated.value) {
      return NextResponse.json({ error: "Invalid run input", issues: validated.issues }, { status: 400 });
    }
    const agentId = typeof (body as Record<string, unknown>).agentId === "string"
      ? ((body as Record<string, unknown>).agentId as string)
      : undefined;
    const background = (body as Record<string, unknown>).background === true;

    const identityHeaders = await runtimeIdentityHeaders(request);
    const result = await startRun({ input: validated.value, agentId, identityHeaders }, { background });
    const isBackground = "status" in result && !("modelSteps" in result);
    return NextResponse.json({ success: true, ...result }, { status: isBackground ? 202 : 200 });
  } catch (err) {
    return errorResponse(err, "[api/harness/runs] POST");
  }
}

// GET /api/harness/runs — recent runs, read from the runtime.
export async function GET() {
  try {
    const runs = await listRunsFromRuntime(50);
    return NextResponse.json({ success: true, runs });
  } catch (err) {
    return errorResponse(err, "[api/harness/runs] GET");
  }
}

function errorResponse(err: unknown, label: string) {
  const error = toHarnessErrorJson(err);
  const status =
    err instanceof HarnessRuntimeUnavailable ? 503
    : err instanceof HarnessError && err.code === "PROVIDER_NOT_CONFIGURED" ? 503
    : err instanceof HarnessError && err.code === "INVALID_INPUT" ? 400
    : 500;
  console.error(`${label} error:`, error.message);
  return NextResponse.json({ error: error.message, code: error.code }, { status });
}

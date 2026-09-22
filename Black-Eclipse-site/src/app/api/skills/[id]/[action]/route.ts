import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import {
  enableSkill,
  disableSkill,
  deprecateSkill,
  rollbackSkill,
  isOperatorRequest,
} from "@/lib/harness/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/skills/:id/:action — lifecycle actions. Enable/disable/deprecate/
// rollback all require operator authorization, derived server-side.
const ACTIONS = new Set(["enable", "disable", "deprecate", "rollback"]);

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string; action: string }> }
) {
  const { id, action } = await params;
  if (!ACTIONS.has(action)) {
    return NextResponse.json({ error: `unsupported action: ${action}` }, { status: 404 });
  }
  const blocked = guardMutation(request, `skill-${action}`);
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const operator = isOperatorRequest(request);
    const version = typeof body.version === "string" ? body.version : undefined;
    let result: Record<string, unknown>;
    if (action === "enable") result = (await enableSkill(id, operator, version)) as Record<string, unknown>;
    else if (action === "disable") result = (await disableSkill(id, operator, version)) as Record<string, unknown>;
    else if (action === "deprecate")
      result = (await deprecateSkill(
        id,
        operator,
        typeof body.reason === "string" ? body.reason : "deprecated",
        typeof body.supersededBy === "string" ? body.supersededBy : undefined
      )) as Record<string, unknown>;
    else
      result = (await rollbackSkill(
        id,
        operator,
        typeof body.version === "string" ? body.version : "",
        typeof body.reason === "string" ? body.reason : "rollback"
      )) as Record<string, unknown>;
    return NextResponse.json(result, { status: result.success ? 200 : 403 });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : `${action} failed` },
      { status: unavailable ? 503 : 500 }
    );
  }
}

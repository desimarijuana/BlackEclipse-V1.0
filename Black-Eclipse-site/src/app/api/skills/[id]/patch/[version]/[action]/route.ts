import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import {
  activateSkillVersion,
  checkSkillRollback,
  evaluateSkillVersion,
  isOperatorRequest,
  promoteSkillCanary,
} from "@/lib/harness/clients/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/skills/:id/patch/:version/:action — evaluate / activate / promote /
// auto-rollback-check. All require operator authorization, derived server-side.
const ACTIONS = new Set(["evaluate", "activate", "promote", "auto-rollback-check"]);

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string; version: string; action: string }> }
) {
  const { id, version, action } = await params;
  if (!ACTIONS.has(action)) {
    return NextResponse.json({ error: `unsupported action: ${action}` }, { status: 404 });
  }
  const blocked = guardMutation(request, `skill-patch-${action}`);
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const operator = isOperatorRequest(request);
    let result: Record<string, unknown>;
    if (action === "evaluate") result = (await evaluateSkillVersion(id, version, operator)) as Record<string, unknown>;
    else if (action === "activate")
      result = (await activateSkillVersion(
        id, version, operator,
        Boolean(body.canary),
        typeof body.reason === "string" ? body.reason : "",
      )) as Record<string, unknown>;
    else if (action === "promote") result = (await promoteSkillCanary(id, version, operator)) as Record<string, unknown>;
    else
      result = (await checkSkillRollback(
        id, version, operator,
        typeof body.userCorrections === "number" ? body.userCorrections : 0,
      )) as Record<string, unknown>;
    return NextResponse.json(result, { status: result.success === false ? 403 : 200 });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : `${action} failed` },
      { status: unavailable ? 503 : 500 }
    );
  }
}

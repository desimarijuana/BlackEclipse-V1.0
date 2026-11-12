import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import {
  createAutomation,
  listAutomations,
  type AutomationState,
  type CreateAutomationInput,
} from "@/lib/harness/clients/automation-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const scopeId = url.searchParams.get("scopeId") ?? undefined;
    const state = (url.searchParams.get("state") as AutomationState | null) ?? undefined;
    const automations = await listAutomations(scopeId, state);
    return NextResponse.json({ success: true, automations });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "automation list failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}

export async function POST(request: Request) {
  const blocked = guardMutation(request, "automation-create");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = (await request.json().catch(() => ({}))) as CreateAutomationInput;
    const automation = await createAutomation(body);
    return NextResponse.json({ success: true, automation });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "automation create failed" },
      { status: 400 },
    );
  }
}

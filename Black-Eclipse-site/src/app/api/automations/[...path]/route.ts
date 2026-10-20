import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { HarnessRuntimeUnavailable } from "@/lib/harness";
import {
  archiveAutomation,
  cancelAutomationExecution,
  deleteAutomation,
  disableAutomation,
  dryRunAutomation,
  enableAutomation,
  getAutomation,
  getAutomationExecution,
  getAutomationMetrics,
  getAutomationStatus,
  getAutomationStatuses,
  getAutomationTimeline,
  listAutomationHistory,
  listAutomationVersions,
  pauseAutomation,
  resetAutomationBreaker,
  resumeAutomation,
  resumeAutomationExecution,
  runAutomationNow,
  testAutomation,
  updateAutomation,
  validateAutomation,
} from "@/lib/harness/automation-client";

export const dynamic = "force-dynamic";

const LIFECYCLE: Record<string, (id: string) => Promise<unknown>> = {
  enable: enableAutomation,
  disable: disableAutomation,
  pause: pauseAutomation,
  resume: resumeAutomation,
  archive: archiveAutomation,
  "reset-breaker": resetAutomationBreaker,
};

function fail(err: unknown, fallback: string) {
  const unavailable = err instanceof HarnessRuntimeUnavailable;
  return NextResponse.json(
    { error: err instanceof Error ? err.message : fallback },
    { status: unavailable ? 503 : 400 },
  );
}

async function handle(request: Request, path: string[], method: string): Promise<Response> {
  // ── metrics ──────────────────────────────────────────────────────────────
  if (path.length === 1 && path[0] === "metrics" && method === "GET") {
    return NextResponse.json({ success: true, metrics: await getAutomationMetrics() });
  }

  // ── statuses (batch) ─────────────────────────────────────────────────────
  // One round-trip for every bot's latest run. Must be handled BEFORE the
  // `{id}` branch, otherwise "statuses" is treated as an automation id.
  if (path.length === 1 && path[0] === "statuses" && method === "GET") {
    return NextResponse.json({ success: true, statuses: await getAutomationStatuses() });
  }

  // ── executions/{id}[/timeline|cancel] ────────────────────────────────────
  if (path[0] === "executions") {
    const executionId = path[1];
    if (!executionId) return NextResponse.json({ error: "missing execution id" }, { status: 400 });
    if (path.length === 2 && method === "GET") {
      return NextResponse.json({ success: true, execution: await getAutomationExecution(executionId) });
    }
    if (path.length === 3 && path[2] === "timeline" && method === "GET") {
      return NextResponse.json({ success: true, timeline: await getAutomationTimeline(executionId) });
    }
    if (path.length === 3 && path[2] === "cancel" && method === "POST") {
      await cancelAutomationExecution(executionId);
      return NextResponse.json({ success: true, cancelled: executionId });
    }
    if (path.length === 3 && path[2] === "resume" && method === "POST") {
      await resumeAutomationExecution(executionId);
      return NextResponse.json({ success: true, resumed: executionId });
    }
    return NextResponse.json({ error: `unsupported route ${method} executions/${path.slice(1).join("/")}` }, { status: 404 });
  }

  // ── {id} ─────────────────────────────────────────────────────────────────
  const id = path[0];
  if (!id) return NextResponse.json({ error: "missing automation id" }, { status: 400 });

  if (path.length === 1) {
    if (method === "GET") return NextResponse.json({ success: true, automation: await getAutomation(id) });
    if (method === "PATCH") {
      const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
      return NextResponse.json({ success: true, automation: await updateAutomation(id, body) });
    }
    if (method === "DELETE") {
      await deleteAutomation(id);
      return NextResponse.json({ success: true, deleted: id });
    }
  }

  // ── {id}/{action} ────────────────────────────────────────────────────────
  const action = path[1];
  if (path.length === 2 && action) {
    if (method === "POST" && LIFECYCLE[action]) {
      return NextResponse.json({ success: true, automation: await LIFECYCLE[action](id) });
    }
    if (method === "POST" && action === "run") {
      return NextResponse.json({ success: true, ...(await runAutomationNow(id)) });
    }
    if (method === "POST" && action === "dry-run") {
      return NextResponse.json({ success: true, dryRun: await dryRunAutomation(id) });
    }
    if (method === "POST" && action === "test") {
      return NextResponse.json({ success: true, ...(await testAutomation(id)) });
    }
    if (method === "POST" && action === "validate") {
      return NextResponse.json({ success: true, ...(await validateAutomation(id)) });
    }
    if (method === "GET" && action === "status") {
      return NextResponse.json({ success: true, status: await getAutomationStatus(id) });
    }
    if (method === "GET" && action === "history") {
      return NextResponse.json({ success: true, executions: await listAutomationHistory(id) });
    }
    if (method === "GET" && action === "versions") {
      return NextResponse.json({ success: true, versions: await listAutomationVersions(id) });
    }
  }

  return NextResponse.json({ error: `unsupported route ${method} ${path.join("/")}` }, { status: 404 });
}

export async function GET(request: Request, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  try {
    return await handle(request, path, "GET");
  } catch (err) {
    return fail(err, "automation read failed");
  }
}

export async function POST(request: Request, ctx: { params: Promise<{ path: string[] }> }) {
  const blocked = guardMutation(request, "automation-action");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const { path } = await ctx.params;
  try {
    return await handle(request, path, "POST");
  } catch (err) {
    return fail(err, "automation action failed");
  }
}

export async function PATCH(request: Request, ctx: { params: Promise<{ path: string[] }> }) {
  const blocked = guardMutation(request, "automation-update");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const { path } = await ctx.params;
  try {
    return await handle(request, path, "PATCH");
  } catch (err) {
    return fail(err, "automation update failed");
  }
}

export async function DELETE(request: Request, ctx: { params: Promise<{ path: string[] }> }) {
  const blocked = guardMutation(request, "automation-delete");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const { path } = await ctx.params;
  try {
    return await handle(request, path, "DELETE");
  } catch (err) {
    return fail(err, "automation delete failed");
  }
}

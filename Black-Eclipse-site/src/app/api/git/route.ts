import { NextResponse } from "next/server";
import { guardExpensiveMutation } from "@/lib/api-guard";
import { HarnessRuntimeUnavailable } from "@/lib/harness";
import {
  commit as engineCommit,
  draftCommitMessage as engineDraft,
  getDiff as engineDiff,
  getLog as engineLog,
  getStatus as engineStatus,
  push as enginePush,
  stage as engineStage,
  unstage as engineUnstage,
} from "@/lib/git/service";

export const dynamic = "force-dynamic";
export const maxDuration = 120;

// /api/git — the in-app git workflow (status → stage → commit → push).
//
// GET  ?action=status|diff|log|draft
// POST { action: "stage"|"unstage"|"commit"|"push", ... }
//
// A THIN proxy over the Python runtime's `/git/*` routes. The engine (discovery,
// journal, lock, risk/authorization, recovery) lives in `python/harness/git/`;
// this route adds no Git logic. It is loopback/same-origin guarded, and the
// runtime route it calls is independently operator-gated. Commits and pushes are
// separate, explicit actions — a commit never pushes, and push is never forced.
//
// When the Python runtime is unavailable the route returns 503 honestly rather
// than falling back to a second (TS) git implementation.

function errorResponse(err: unknown) {
  if (err instanceof HarnessRuntimeUnavailable) {
    return NextResponse.json({ error: err.message, code: "RUNTIME_UNAVAILABLE" }, { status: 503 });
  }
  const code = (err as { code?: string })?.code;
  const status = code === "GIT_UNAVAILABLE" || code === "RUNTIME_UNAVAILABLE" ? 503 : 400;
  return NextResponse.json(
    { error: err instanceof Error ? err.message : "Git operation failed", code },
    { status },
  );
}

export async function GET(request: Request) {
  const action = new URL(request.url).searchParams.get("action") ?? "status";
  try {
    switch (action) {
      case "status":
        return NextResponse.json({ success: true, status: await engineStatus() });
      case "diff": {
        const staged = new URL(request.url).searchParams.get("staged") === "1";
        return NextResponse.json({ success: true, diff: await engineDiff(staged) });
      }
      case "log":
        return NextResponse.json({ success: true, commits: await engineLog() });
      case "draft":
        return NextResponse.json({ success: true, message: await engineDraft() });
      default:
        return NextResponse.json({ error: `Unknown action: ${action}` }, { status: 400 });
    }
  } catch (err) {
    return errorResponse(err);
  }
}

export async function POST(request: Request) {
  const blocked = guardExpensiveMutation(request, "git", { limit: 60, windowMs: 60_000 });
  if (blocked) {
    return NextResponse.json(blocked.body, { status: blocked.status, headers: blocked.headers });
  }
  try {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const action = typeof body.action === "string" ? body.action : "";

    switch (action) {
      case "stage": {
        const paths = Array.isArray(body.paths)
          ? body.paths.filter((p): p is string => typeof p === "string")
          : [];
        await engineStage(paths);
        return NextResponse.json({ success: true, status: await engineStatus() });
      }
      case "unstage": {
        const paths = Array.isArray(body.paths)
          ? body.paths.filter((p): p is string => typeof p === "string")
          : [];
        await engineUnstage(paths);
        return NextResponse.json({ success: true, status: await engineStatus() });
      }
      case "commit": {
        const message = typeof body.message === "string" ? body.message : "";
        const result = await engineCommit(message);
        return NextResponse.json({ success: true, commit: result, status: await engineStatus() });
      }
      case "push": {
        const setUpstream = body.setUpstream === true;
        const result = await enginePush(setUpstream);
        return NextResponse.json({ success: true, push: result, status: await engineStatus() });
      }
      default:
        return NextResponse.json({ error: `Unknown action: ${action}` }, { status: 400 });
    }
  } catch (err) {
    return errorResponse(err);
  }
}

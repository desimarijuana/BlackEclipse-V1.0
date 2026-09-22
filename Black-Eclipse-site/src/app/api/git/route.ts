import { NextResponse } from "next/server";
import { guardExpensiveMutation } from "@/lib/api-guard";
import { GitError } from "@/lib/git/service";
import {
  commit,
  draftCommitMessage,
  getDiff,
  getLog,
  getStatus,
  push,
  stage,
  unstage,
} from "@/lib/git/service";

export const dynamic = "force-dynamic";
export const maxDuration = 120;

// /api/git — the in-app git workflow (status → stage → commit → push).
//
// GET  ?action=status|diff|log|draft
// POST { action: "stage"|"unstage"|"commit"|"push", ... }
//
// Guarded (loopback/same-origin only). Commits and pushes are explicit, never
// automatic, and the service refuses secret-looking paths. Push is a separate
// action from commit — a commit never pushes.

function statusFor(err: unknown): { status: number; body: { error: string; code?: string } } {
  if (err instanceof GitError) {
    const status =
      err.code === "SECRET_BLOCKED" || err.code === "NOTHING_STAGED" || err.code === "EMPTY_MESSAGE"
        ? 400
        : err.code === "GIT_UNAVAILABLE"
        ? 503
        : 400;
    return { status, body: { error: err.message, code: err.code } };
  }
  console.error("[api/git] error:", err);
  return { status: 500, body: { error: "Git operation failed" } };
}

export async function GET(request: Request) {
  const action = new URL(request.url).searchParams.get("action") ?? "status";
  try {
    switch (action) {
      case "status":
        return NextResponse.json({ success: true, status: await getStatus() });
      case "diff": {
        const staged = new URL(request.url).searchParams.get("staged") === "1";
        return NextResponse.json({ success: true, diff: await getDiff(staged) });
      }
      case "log":
        return NextResponse.json({ success: true, commits: await getLog() });
      case "draft":
        return NextResponse.json({ success: true, message: await draftCommitMessage() });
      default:
        return NextResponse.json({ error: `Unknown action: ${action}` }, { status: 400 });
    }
  } catch (err) {
    const { status, body } = statusFor(err);
    return NextResponse.json(body, { status });
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
        await stage(paths);
        return NextResponse.json({ success: true, status: await getStatus() });
      }
      case "unstage": {
        const paths = Array.isArray(body.paths)
          ? body.paths.filter((p): p is string => typeof p === "string")
          : [];
        await unstage(paths);
        return NextResponse.json({ success: true, status: await getStatus() });
      }
      case "commit": {
        const message = typeof body.message === "string" ? body.message : "";
        const result = await commit(message);
        return NextResponse.json({ success: true, commit: result, status: await getStatus() });
      }
      case "push": {
        const setUpstream = body.setUpstream === true;
        const result = await push(setUpstream);
        return NextResponse.json({ success: true, push: result, status: await getStatus() });
      }
      default:
        return NextResponse.json({ error: `Unknown action: ${action}` }, { status: 400 });
    }
  } catch (err) {
    const { status, body } = statusFor(err);
    return NextResponse.json(body, { status });
  }
}

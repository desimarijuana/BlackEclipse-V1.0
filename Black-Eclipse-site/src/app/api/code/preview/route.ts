import { NextResponse } from "next/server";

import { guardMutation } from "@/lib/api-guard";
import {
  getCodePreview,
  getCodePreviewLogs,
  startCodePreview,
  stopCodePreview,
  type PreviewTarget,
} from "@/lib/harness/clients/code-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

function targetFrom(url: URL): PreviewTarget {
  const taskId = url.searchParams.get("taskId") ?? undefined;
  const rootId = url.searchParams.get("rootId") ?? undefined;
  return { ...(taskId ? { taskId } : {}), ...(rootId ? { rootId } : {}) };
}

function fail(err: unknown, fallback: string) {
  const unavailable = err instanceof HarnessRuntimeUnavailable;
  return NextResponse.json(
    { error: err instanceof Error ? err.message : fallback },
    { status: unavailable ? 503 : 500 },
  );
}

export async function GET(request: Request) {
  const url = new URL(request.url);
  try {
    if (url.searchParams.get("logs") === "1") {
      const tail = Number(url.searchParams.get("tail") ?? 200);
      return NextResponse.json({
        success: true,
        logs: await getCodePreviewLogs(targetFrom(url), Number.isFinite(tail) ? tail : 200),
      });
    }
    return NextResponse.json({ success: true, preview: await getCodePreview(targetFrom(url)) });
  } catch (err) {
    return fail(err, "could not read the preview");
  }
}

export async function POST(request: Request) {
  const blocked = guardMutation(request, "code-preview");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const body = (await request.json().catch(() => ({}))) as PreviewTarget & { action?: string };
  const target: PreviewTarget = {
    ...(body.taskId ? { taskId: body.taskId } : {}),
    ...(body.rootId ? { rootId: body.rootId } : {}),
  };
  try {
    const preview =
      body.action === "stop"
        ? await stopCodePreview(target)
        : await startCodePreview(target);
    return NextResponse.json({ success: preview.status === "ok", preview });
  } catch (err) {
    return fail(err, body.action === "stop" ? "could not stop the preview" : "could not start the preview");
  }
}

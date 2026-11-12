import { NextResponse } from "next/server";

import { getProjectBrief, type PreviewTarget } from "@/lib/harness/clients/code-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const taskId = url.searchParams.get("taskId") ?? undefined;
  const rootId = url.searchParams.get("rootId") ?? undefined;
  const target: PreviewTarget = {
    ...(taskId ? { taskId } : {}),
    ...(rootId ? { rootId } : {}),
  };
  try {
    const project = await getProjectBrief(target);
    return NextResponse.json({ success: true, project });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "could not read the project" },
      { status: unavailable ? 503 : 500 },
    );
  }
}

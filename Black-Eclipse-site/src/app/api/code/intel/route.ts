import { NextResponse } from "next/server";

import { guardMutation } from "@/lib/api-guard";
import { prepareProjectIndex } from "@/lib/harness/clients/code-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

/** Prepare the selected project: index it so search/context are ready. */
export async function POST(request: Request) {
  const blocked = guardMutation(request, "code-project-index");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    return NextResponse.json({ success: true, result: await prepareProjectIndex() });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "could not prepare the project" },
      { status: unavailable ? 503 : 500 },
    );
  }
}

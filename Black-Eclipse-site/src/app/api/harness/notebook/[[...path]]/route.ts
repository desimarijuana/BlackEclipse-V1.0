import { NextResponse } from "next/server";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";
import { runtimeIdentityHeaders } from "@/lib/harness/runtime-identity";
import { guardMutation } from "@/lib/api-guard";

export const dynamic = "force-dynamic";

// /api/harness/notebook/** — the front door to the runtime's notebook routes.
//
//   POST /cells/:id/run     run one cell in the analysis sandbox
//   POST /kernel/restart    drop the conversation's warm kernel
//
// This is a thin pass-through, like the artifact proxy: the runtime owns the
// execution, the bounds, the kernel and the artifact catalog. A cell can take
// up to its own bounded timeout, so the proxy allows longer than a normal JSON
// call but still has a hard ceiling.

type Ctx = { params: Promise<{ path?: string[] }> };

export async function POST(request: Request, ctx: Ctx): Promise<NextResponse> {
  const blocked = guardMutation(request, "notebook");
  if (blocked) {
    return NextResponse.json(blocked.body, { status: blocked.status });
  }
  const healthy = await ensurePythonRuntime();
  if (!healthy) {
    return NextResponse.json(
      { error: "The Python agent runtime is not available. Install the runtime: npm run setup:python" },
      { status: 503 },
    );
  }
  const { path } = await ctx.params;
  const segments = (path ?? []).join("/");
  if (!segments) {
    return NextResponse.json({ error: "a notebook action is required" }, { status: 400 });
  }
  const token = runtimeCallbackToken();
  try {
    const res = await fetch(`${HARNESS_PY_URL}/notebook/${segments}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { "X-Harness-Operator": token } : {}),
        ...(await runtimeIdentityHeaders(request)),
      },
      body: await request.text(),
      cache: "no-store",
      signal: AbortSignal.timeout(150_000),
    });
    const payload = await res.json().catch(() => ({}));
    return NextResponse.json(payload, { status: res.status });
  } catch (err) {
    console.error("[api/harness/notebook] POST error:", err);
    return NextResponse.json({ error: "The notebook is unavailable" }, { status: 503 });
  }
}

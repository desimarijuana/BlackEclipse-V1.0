import { NextResponse } from "next/server";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";

export const dynamic = "force-dynamic";

// POST /api/harness/gallery/[id]/[action] - favourite or clone a published
// strategy. The action is checked here so a typo cannot become an unknown
// route: the runtime only knows `favourite` and `clone`.
export async function POST(
  request: Request,
  ctx: { params: Promise<{ id: string; action: string }> },
) {
  const { id, action } = await ctx.params;
  if (action !== "favourite" && action !== "clone") {
    return NextResponse.json(
      { error: `unknown gallery action ${action}` },
      { status: 422 },
    );
  }
  try {
    await ensurePythonRuntime();
    const operatorToken = runtimeCallbackToken();
    let body: unknown = undefined;
    try {
      body = await request.json();
    } catch {
      body = undefined;
    }
    const res = await fetch(
      new URL(`${HARNESS_PY_URL}/gallery/${encodeURIComponent(id)}/${action}`),
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(operatorToken ? { "X-Harness-Operator": operatorToken } : {}),
        },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
        cache: "no-store",
      },
    );
    const payload = (await res.json().catch(() => ({}))) as {
      detail?: { message?: string } | string;
      error?: string;
    };
    if (!res.ok) {
      const detail = payload.detail;
      const message =
        typeof detail === "object" && detail && "message" in detail
          ? String(detail.message)
          : typeof detail === "string"
            ? detail
            : `the gallery returned ${res.status}`;
      return NextResponse.json({ error: message }, { status: res.status });
    }
    return NextResponse.json(payload);
  } catch (err) {
    console.error("[api/harness/gallery] request failed:", err);
    return NextResponse.json(
      { error: "the gallery is unavailable" },
      { status: 503 },
    );
  }
}

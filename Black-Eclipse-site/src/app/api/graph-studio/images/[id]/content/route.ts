import { NextResponse } from "next/server";
import { HarnessRuntimeUnavailable } from "@/lib/harness";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeProxyHeaders } from "@/lib/harness/runtime-identity";

export const dynamic = "force-dynamic";

// GET /api/graph-studio/images/:id/content — stream the stored image bytes.
export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const healthy = await ensurePythonRuntime();
    if (!healthy) {
      return NextResponse.json({ error: "The Python agent runtime is not available." }, { status: 503 });
    }
    const { id } = await params;
    const res = await fetch(
      `${HARNESS_PY_URL}/graph/assets/images/${encodeURIComponent(id)}/content`,
      {
        headers: await runtimeProxyHeaders(request),
        signal: AbortSignal.timeout(30_000),
      },
    );
    if (!res.ok) {
      return NextResponse.json({ error: `image returned ${res.status}` }, { status: 404 });
    }
    return new Response(await res.arrayBuffer(), {
      headers: {
        "Content-Type": res.headers.get("content-type") ?? "image/png",
        "Cache-Control": "no-store",
      },
    });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "image not found" },
      { status: unavailable ? 503 : 404 },
    );
  }
}

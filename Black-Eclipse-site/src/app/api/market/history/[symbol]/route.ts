import { NextResponse } from "next/server";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";

export const dynamic = "force-dynamic";

// GET /api/market/history/[symbol] - the coverage of one instrument in the
// local data vault. Served from the local copy; no provider is called.
export async function GET(
  request: Request,
  ctx: { params: Promise<{ symbol: string }> },
) {
  try {
    await ensurePythonRuntime();
    const { symbol } = await ctx.params;
    const interval = new URL(request.url).searchParams.get("interval") ?? "1d";
    const operatorToken = runtimeCallbackToken();
    const url = new URL(`${HARNESS_PY_URL}/market/history/${encodeURIComponent(symbol)}`);
    url.searchParams.set("interval", interval);
    const res = await fetch(url, {
      headers: {
        "Content-Type": "application/json",
        ...(operatorToken ? { "X-Harness-Operator": operatorToken } : {}),
      },
      cache: "no-store",
    });
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
            : `the history catalog returned ${res.status}`;
      return NextResponse.json({ error: message }, { status: res.status });
    }
    return NextResponse.json(payload);
  } catch (err) {
    console.error("[api/market/history] GET error:", err);
    return NextResponse.json(
      { error: "the history catalog is unavailable" },
      { status: 503 },
    );
  }
}

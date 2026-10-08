// Thin proxy: /api/search-provider/* -> Python /browser/install*.
//
// Enables JS-rendered retrieval with one click from Settings. The Next.js front
// door only forwards; the Python runtime performs the real, idempotent install
// and reports the binary's true presence. A failure is surfaced honestly, never
// hidden behind a success state.

import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";
import { HarnessRuntimeUnavailable } from "@/lib/harness";
import { redactSecrets } from "@/lib/harness/errors";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const healthy = await ensurePythonRuntime();
    if (!healthy) {
      throw new HarnessRuntimeUnavailable(
        "The Python agent runtime is not available. Install the runtime: npm run setup:python",
      );
    }
    const operatorToken = runtimeCallbackToken();
    const res = await fetch(`${HARNESS_PY_URL}/browser/install`, {
      headers: operatorToken ? { "X-Harness-Operator": operatorToken } : {},
      signal: AbortSignal.timeout(30_000),
    });
    const payload = await res.json().catch(() => ({}));
    if (!res.ok) {
      return NextResponse.json({ error: "browser install status unavailable" }, { status: res.status });
    }
    return NextResponse.json(payload);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "runtime request failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}

export async function POST(request: Request) {
  const blocked = guardMutation(request, "browser-install");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const healthy = await ensurePythonRuntime();
    if (!healthy) {
      throw new HarnessRuntimeUnavailable(
        "The Python agent runtime is not available. Install the runtime: npm run setup:python",
      );
    }
    const operatorToken = runtimeCallbackToken();
    const res = await fetch(`${HARNESS_PY_URL}/browser/install`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(operatorToken ? { "X-Harness-Operator": operatorToken } : {}),
      },
      body: JSON.stringify({ with_deps: true }),
      signal: AbortSignal.timeout(960_000),
    });
    const payload = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = (payload as { detail?: unknown }).detail;
      return NextResponse.json(
        { error: redactSecrets(typeof detail === "string" ? detail : `browser install failed (HTTP ${res.status})`) },
        { status: res.status },
      );
    }
    return NextResponse.json(payload);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "browser install failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}

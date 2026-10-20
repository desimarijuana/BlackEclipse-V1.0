// ── SDK lock checks for the Next.js front door ──────────────────────────────
// The design lock must protect BOTH the SDK route and the existing Settings
// theme editor (`/api/theme`). This helper asks the Python runtime's lock gate
// before either surface persists a design. A runtime that is not running cannot
// hold locks, so the local edit proceeds (zero-config boot still works).

import { NextResponse } from "next/server";
import { HARNESS_PY_URL, pythonRuntimeReachable } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";
import { runtimeIdentityHeaders } from "@/lib/harness/runtime-identity";

async function lockedFor(request: Request, resourceType: "theme" | "design"): Promise<NextResponse | null> {
  const token = runtimeCallbackToken();
  const unlock = request.headers.get("x-eclipse-unlock");
  const user = request.headers.get("x-eclipse-user");
  let identity: Record<string, string> = {};
  try {
    identity = await runtimeIdentityHeaders(request);
  } catch {
    identity = {};
  }
  const res = await fetch(`${HARNESS_PY_URL}/sdk/locks/assert`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { "X-Harness-Operator": token } : {}),
      ...(unlock ? { "X-Eclipse-Unlock": unlock } : {}),
      ...(user ? { "X-Harness-User": user } : {}),
      ...identity,
    },
    body: JSON.stringify({ resourceType, resourceId: "global", action: "write" }),
    signal: AbortSignal.timeout(8_000),
  });
  if (res.status === 423) {
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: 423 });
  }
  return null;
}

export async function designLockBlocked(request: Request): Promise<NextResponse | null> {
  try {
    // Probe only — never spawn the runtime just to look for a lock.
    if (!(await pythonRuntimeReachable())) return null;
    return (await lockedFor(request, "theme")) ?? (await lockedFor(request, "design"));
  } catch {
    /* lock service unavailable — do not block the local design edit */
  }
  return null;
}

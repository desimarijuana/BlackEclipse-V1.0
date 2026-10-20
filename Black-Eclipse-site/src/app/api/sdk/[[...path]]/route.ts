// ─── Eclipse SDK API ──────────────────────────────────────────────────────────
// ONE front door for the user-facing extension surface.
//
//   /api/sdk/design        → the app-wide theme (JDDS SystemConfig), patched
//   /api/sdk/capabilities  → the runtime manifest, merged with design support
//   /api/sdk/*             → proxied to the Python `/sdk/*` group
//
// The Python runtime is authoritative for widgets, pages, funds and locks; the
// theme stays where it already lives (the Next.js server + JDDS). Mutations pass
// the shared CSRF/origin guard, and the user's `X-Eclipse-Unlock` token is
// forwarded so locked resources are enforced on the Python side.

import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { HARNESS_PY_URL, ensurePythonRuntime } from "@/lib/harness/python-runtime";
import { runtimeCallbackToken } from "@/lib/harness/runtime-auth";
import { runtimeIdentityHeaders } from "@/lib/harness/runtime-identity";
import {
  clearServerTheme,
  getServerThemeState,
  setServerTheme,
} from "@/lib/theme/server";
import { DEFAULT_ECLIPSE_THEME, THEME_PRESETS, normalizeTheme } from "@/lib/theme/tokens";
import { baseDesignTheme, mergeThemePatch } from "@/lib/sdk/design";
import { designLockBlocked } from "@/lib/sdk/locks-server";
import { themeRoute } from "@/lib/sdk/theme-server";
import { appRoute } from "@/lib/sdk/app-server";
import { recordSdkAudit } from "@/lib/sdk/audit-server";
import { dashboardRoute, isDashboardTemplateRoute } from "@/lib/sdk/dashboard-server";

export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ path?: string[] }> };

function pythonHeaders(request: Request, token: string | null | undefined): Record<string, string> {
  const unlock = request.headers.get("x-eclipse-unlock");
  const user = request.headers.get("x-eclipse-user");
  return {
    "Content-Type": "application/json",
    ...(token ? { "X-Harness-Operator": token } : {}),
    ...(unlock ? { "X-Eclipse-Unlock": unlock } : {}),
    ...(user ? { "X-Harness-User": user } : {}),
  };
}

async function identityHeaders(request: Request): Promise<Record<string, string>> {
  try {
    return await runtimeIdentityHeaders(request);
  } catch {
    return {};
  }
}

async function proxyPython(request: Request, segments: string, method: string): Promise<NextResponse> {
  const healthy = await ensurePythonRuntime();
  if (!healthy) {
    return NextResponse.json(
      { error: "The Python agent runtime is not available. Install the runtime: npm run setup:python" },
      { status: 503 },
    );
  }
  const url = new URL(request.url);
  const target = segments === "" ? "/sdk" : `/sdk/${segments}`;
  const init: RequestInit = {
    method,
    headers: {
      ...pythonHeaders(request, runtimeCallbackToken()),
      ...(await identityHeaders(request)),
    },
    signal: AbortSignal.timeout(60_000),
  };
  if (method !== "GET" && method !== "DELETE") init.body = await request.text();
  try {
    const res = await fetch(`${HARNESS_PY_URL}${target}${url.search}`, init);
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "sdk request failed" },
      { status: 502 },
    );
  }
}

function designManifest(state: { theme: unknown; initialized: boolean }) {
  return {
    canApply: true,
    hasSavedTheme: Boolean(state.theme),
    initialized: state.initialized,
    presets: THEME_PRESETS.map(({ id, label, description, theme }) => ({
      id,
      label,
      description,
      primary: theme.colors.primary,
      scheme: theme.scheme,
    })),
  };
}

async function designRoute(request: Request, method: string): Promise<NextResponse> {
  if (method !== "GET") {
    const blocked = guardMutation(request, "sdk");
    if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  }
  try {
    const state = await getServerThemeState();
    if (method === "GET") {
      return NextResponse.json({
        success: true,
        theme: state.theme ?? DEFAULT_ECLIPSE_THEME,
        initialized: state.initialized,
        design: designManifest(state),
      });
    }
    const blocked = await designLockBlocked(request);
    if (blocked) return blocked;
    if (method === "DELETE") {
      await clearServerTheme();
      await recordSdkAudit(request, {
        action: "theme.reset",
        summary: "Reset the app-wide design",
        resourceType: "theme",
        resourceId: "global",
      });
      return NextResponse.json({ success: true, theme: DEFAULT_ECLIPSE_THEME });
    }
    const body = (await request.json().catch(() => ({}))) as { patch?: unknown; theme?: unknown };
    const theme = body.theme
      ? normalizeTheme(body.theme)
      : mergeThemePatch(baseDesignTheme(state.theme), body.patch);
    const saved = await setServerTheme(theme);
    await recordSdkAudit(request, {
      action: "theme.apply",
      summary: "Updated the app-wide design",
      resourceType: "theme",
      resourceId: "global",
    });
    return NextResponse.json({ success: true, theme: saved });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "design request failed" },
      { status: 500 },
    );
  }
}

async function capabilitiesRoute(request: Request): Promise<NextResponse> {
  const state = await getServerThemeState();
  const design = designManifest(state);
  let runtime: Record<string, unknown> | null = null;
  try {
    if (await ensurePythonRuntime()) {
      const res = await fetch(`${HARNESS_PY_URL}/sdk/capabilities`, {
        headers: {
          ...pythonHeaders(request, runtimeCallbackToken()),
          ...(await identityHeaders(request)),
        },
        signal: AbortSignal.timeout(15_000),
      });
      if (res.ok) runtime = (await res.json().catch(() => null)) as Record<string, unknown> | null;
    }
  } catch {
    runtime = null;
  }
  if (!runtime) {
    return NextResponse.json({
      success: true,
      sdkVersion: "1.0.0",
      runtime: "unavailable",
      widgets: { canCreate: false, canDelete: false, count: 0 },
      pages: { canCreate: false, canCompose: false },
      portfolio: { available: false, canAddStock: false, canCreateFund: false },
      locks: { canCreate: false, canUnlock: false, resources: ["page", "widget", "portfolio", "design"] },
      design,
    });
  }
  return NextResponse.json({ ...runtime, design, runtime: "available" });
}

async function handle(request: Request, ctx: Ctx, method: string): Promise<Response> {
  const { path } = await ctx.params;
  const segments = (path ?? []).join("/");
  if (segments === "app" || segments.startsWith("app/")) {
    return appRoute(request, method, path ?? []);
  }
  if (isDashboardTemplateRoute(path ?? [])) {
    const handled = await dashboardRoute(request, method, path ?? []);
    if (handled) return handled;
  }
  if (segments === "design") return designRoute(request, method);
  if (segments === "theme" || segments.startsWith("theme/")) {
    return themeRoute(request, method, path ?? []);
  }
  if (segments === "capabilities" && method === "GET") return capabilitiesRoute(request);
  if (method !== "GET") {
    const blocked = guardMutation(request, "sdk");
    if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  }
  return proxyPython(request, segments, method);
}

export async function GET(request: Request, ctx: Ctx) {
  return handle(request, ctx, "GET");
}
export async function POST(request: Request, ctx: Ctx) {
  return handle(request, ctx, "POST");
}
export async function PUT(request: Request, ctx: Ctx) {
  return handle(request, ctx, "PUT");
}
export async function PATCH(request: Request, ctx: Ctx) {
  return handle(request, ctx, "PATCH");
}
export async function DELETE(request: Request, ctx: Ctx) {
  return handle(request, ctx, "DELETE");
}

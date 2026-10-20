// ── App shell HTTP surface (`/api/sdk/app*`) ─────────────────────────────────
// Local Next routes, not proxied to Python: the nav config lives in JDDS
// `SystemConfig` and the open shells subscribe to this process over SSE. The
// Python `sdk_app_*` tools reach these routes over the loopback callback.
//
//   GET    /api/sdk/app            read the app-wide nav + manifest
//   PUT    /api/sdk/app            update order/visibility/mode
//   DELETE /api/sdk/app            reset to the shipped nav
//   POST   /api/sdk/app/navigate   open a tab/page/dashboard in connected shells
//   GET    /api/sdk/app/stream     SSE: `nav` updates + `navigate` commands

import { NextResponse } from 'next/server';
import { guardMutation } from '@/lib/api-guard';
import { APP_TABS } from '@/lib/search/deep-link';
import { recordSdkAudit } from './audit-server';
import {
  APP_NAV_MODES,
  APP_NAV_SECTIONS,
  isAppNavMode,
  type AppNavigateTarget,
} from './app-shell-types';
import {
  getAppShellState,
  publishNavigation,
  resetAppShellNav,
  subscribeAppShell,
  updateAppShellNav,
} from './app-shell';

const HEARTBEAT_MS = 15_000;

function fail(message: string, status = 400): NextResponse {
  return NextResponse.json({ error: message }, { status });
}

function statePayload(state: Awaited<ReturnType<typeof getAppShellState>>) {
  return {
    success: true,
    ...state,
    sections: APP_NAV_SECTIONS,
    modes: APP_NAV_MODES,
  };
}

function parseTarget(raw: unknown): AppNavigateTarget | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null;
  const value = raw as Record<string, unknown>;
  const tab = typeof value.tab === 'string' ? value.tab.trim() : '';
  if (!(APP_TABS as readonly string[]).includes(tab)) return null;
  const target: AppNavigateTarget = { tab: tab as AppNavigateTarget['tab'] };
  if (typeof value.page === 'string' && value.page.trim()) target.page = value.page.trim().slice(0, 300);
  if (typeof value.dashboardId === 'string' && value.dashboardId.trim()) {
    target.dashboardId = value.dashboardId.trim().slice(0, 240);
  }
  if (typeof value.subroute === 'string' && value.subroute.trim()) {
    target.subroute = value.subroute.trim().slice(0, 200);
  }
  if (value.params && typeof value.params === 'object' && !Array.isArray(value.params)) {
    const params: Record<string, string> = {};
    for (const [key, entry] of Object.entries(value.params as Record<string, unknown>)) {
      if (typeof entry === 'string' && key.trim()) params[key.trim().slice(0, 80)] = entry.slice(0, 400);
    }
    if (Object.keys(params).length > 0) target.params = params;
  }
  return target;
}

function stream(request: Request): Response {
  const encoder = new TextEncoder();
  let closed = false;
  let heartbeat: ReturnType<typeof setInterval> | null = null;
  let unsubscribe: (() => void) | null = null;

  const stop = () => {
    closed = true;
    if (heartbeat) clearInterval(heartbeat);
    heartbeat = null;
    unsubscribe?.();
    unsubscribe = null;
  };

  const body = new ReadableStream({
    async start(controller) {
      const send = (event: string, data: unknown) => {
        if (closed) return;
        try {
          controller.enqueue(encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`));
        } catch {
          stop();
        }
      };

      controller.enqueue(encoder.encode(': connected\n\n'));
      try {
        send('nav', await getAppShellState());
      } catch {
        /* the initial frame is best-effort; a later update still lands */
      }
      unsubscribe = subscribeAppShell((event) => {
        if (event.type === 'nav') send('nav', event.state);
        else send('navigate', { target: event.target });
      });
      heartbeat = setInterval(() => {
        if (closed) return;
        try {
          controller.enqueue(encoder.encode(': ping\n\n'));
        } catch {
          stop();
        }
      }, HEARTBEAT_MS);

      request.signal.addEventListener('abort', () => {
        stop();
        try {
          controller.close();
        } catch {
          /* already closed */
        }
      });
    },
    cancel() {
      stop();
    },
  });

  return new Response(body, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache, no-transform',
      Connection: 'keep-alive',
      'X-Accel-Buffering': 'no',
    },
  });
}

export async function appRoute(request: Request, method: string, path: string[]): Promise<Response> {
  const segments = path.filter(Boolean);
  const sub = segments.slice(1);

  if (sub.length === 1 && sub[0] === 'stream' && method === 'GET') {
    return stream(request);
  }

  if (sub.length === 1 && sub[0] === 'navigate' && method === 'POST') {
    const blocked = guardMutation(request, 'sdk-app');
    if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
    const body = (await request.json().catch(() => ({}))) as { target?: unknown };
    const target = parseTarget(body.target);
    if (!target) return fail('a valid target.tab is required');
    publishNavigation(target);
    await recordSdkAudit(request, {
      action: 'app.navigate',
      summary: `Opened ${target.tab}`,
      resourceType: 'app',
      resourceId: target.tab,
      detail: { ...target },
    });
    return NextResponse.json({ success: true, target });
  }

  if (sub.length > 0) return fail('unknown app route', 404);

  if (method === 'GET') {
    return NextResponse.json(statePayload(await getAppShellState()));
  }

  if (method === 'PUT' || method === 'PATCH') {
    const blocked = guardMutation(request, 'sdk-app');
    if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
    const body = (await request.json().catch(() => ({}))) as { nav?: unknown; sections?: unknown; mode?: unknown };
    const patch = body.nav && typeof body.nav === 'object' && !Array.isArray(body.nav)
      ? body.nav as Record<string, unknown>
      : body as Record<string, unknown>;
    if (patch.mode !== undefined && !isAppNavMode(patch.mode)) {
      return fail(`mode must be one of: ${APP_NAV_MODES.join(', ')}`);
    }
    const state = await updateAppShellNav(body.nav ?? body);
    await recordSdkAudit(request, {
      action: 'app.nav_update',
      summary: 'Updated the app navigation',
      resourceType: 'app',
      resourceId: 'nav',
      detail: {
        mode: state.nav.mode,
        visibleSections: state.nav.sections.filter((section) => section.enabled).length,
      },
    });
    return NextResponse.json(statePayload(state));
  }

  if (method === 'DELETE') {
    const blocked = guardMutation(request, 'sdk-app');
    if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
    const state = await resetAppShellNav();
    await recordSdkAudit(request, {
      action: 'app.nav_reset',
      summary: 'Reset the app navigation',
      resourceType: 'app',
      resourceId: 'nav',
    });
    return NextResponse.json(statePayload(state));
  }

  return fail('method not allowed', 405);
}

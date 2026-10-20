// ── Dashboard template/reset routes ──────────────────────────────────────────
// The persona templates are TypeScript (`src/lib/dashboard/templates.ts`), so
// these two operations are built HERE and written through the runtime's
// revision-guarded layout API. The Python tools call these routes over the
// loopback callback; `eclipseSdk.dashboards` calls them directly.

import { NextResponse } from 'next/server';
import { guardMutation } from '@/lib/api-guard';
import { HARNESS_PY_URL, ensurePythonRuntime } from '@/lib/harness/python-runtime';
import { runtimeProxyHeaders } from '@/lib/harness/runtime-identity';
import type { WorkspaceLayout } from '@/lib/workspace/types';
import { recordSdkAudit } from './audit-server';
import {
  buildDashboardTemplateLayout,
  buildDefaultDashboardLayout,
  listDashboardTemplates,
} from './dashboard-templates';

function fail(message: string, status = 400): NextResponse {
  return NextResponse.json({ error: message }, { status });
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

async function headers(request: Request): Promise<Record<string, string>> {
  const out = await runtimeProxyHeaders(request, { json: true });
  const unlock = request.headers.get('x-eclipse-unlock');
  const user = request.headers.get('x-eclipse-user');
  if (unlock) out['X-Eclipse-Unlock'] = unlock;
  if (user) out['X-Harness-User'] = user;
  return out;
}

interface Snapshot {
  status: number;
  data: Record<string, unknown>;
}

async function getSnapshot(id: string, request: Request): Promise<Snapshot> {
  const target = id.toLowerCase() === 'active'
    ? `${HARNESS_PY_URL}/sdk/dashboards/active`
    : `${HARNESS_PY_URL}/sdk/dashboards/${encodeURIComponent(id)}`;
  const res = await fetch(target, {
    headers: await headers(request),
    signal: AbortSignal.timeout(15_000),
    cache: 'no-store',
  });
  const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  return { status: res.status, data };
}

function snapshotId(data: Record<string, unknown>): string | null {
  const dashboard = isRecord(data.dashboard) ? data.dashboard : null;
  const id = dashboard?.dashboardId;
  return typeof id === 'string' && id.trim() ? id.trim() : null;
}

function snapshotRevision(data: Record<string, unknown>): number | null {
  const revision = data.revision;
  return typeof revision === 'number' && Number.isInteger(revision) && revision > 0 ? revision : null;
}

async function putLayout(
  id: string,
  layout: WorkspaceLayout,
  expectedRevision: number,
  request: Request,
): Promise<Snapshot> {
  const res = await fetch(`${HARNESS_PY_URL}/sdk/dashboards/${encodeURIComponent(id)}/layout`, {
    method: 'PUT',
    headers: await headers(request),
    body: JSON.stringify({ layout, expectedRevision }),
    signal: AbortSignal.timeout(30_000),
  });
  const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  return { status: res.status, data };
}

/**
 * Intercept only the template/reset paths; every other dashboard call stays on
 * the generic Python proxy.
 */
export function isDashboardTemplateRoute(path: string[]): boolean {
  const segments = path.filter(Boolean);
  if (segments[0] !== 'dashboards') return false;
  if (segments.length === 2 && segments[1] === 'templates') return true;
  return segments.length === 3 && (segments[2] === 'template' || segments[2] === 'reset');
}

export async function dashboardRoute(
  request: Request,
  method: string,
  path: string[],
): Promise<Response | null> {
  if (!isDashboardTemplateRoute(path)) return null;
  const segments = path.filter(Boolean);

  if (segments[1] === 'templates') {
    if (method !== 'GET') return fail('method not allowed', 405);
    return NextResponse.json({ success: true, templates: listDashboardTemplates() });
  }

  if (method !== 'POST') return fail('method not allowed', 405);
  const blocked = guardMutation(request, 'sdk-dashboard-template');
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });

  if (!(await ensurePythonRuntime())) {
    return fail('The Python agent runtime is not available. Install the runtime: npm run setup:python', 503);
  }

  const requestedId = (segments[1] || '').trim();
  if (!requestedId) return fail('a dashboard id is required');

  const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
  const market = typeof body.market === 'string' && body.market.trim() ? body.market.trim() : 'US';
  const explicitRevision = typeof body.expectedRevision === 'number'
    && Number.isInteger(body.expectedRevision) && body.expectedRevision > 0
    ? body.expectedRevision
    : null;

  let layout: WorkspaceLayout;
  try {
    if (segments[2] === 'reset') {
      layout = buildDefaultDashboardLayout({ market });
    } else {
      const templateId = typeof body.templateId === 'string' ? body.templateId.trim() : '';
      if (!templateId) return fail('templateId is required');
      layout = buildDashboardTemplateLayout(templateId, { market });
    }
  } catch (err) {
    return fail(err instanceof Error ? err.message : 'could not build the dashboard layout', 400);
  }

  const current = await getSnapshot(requestedId, request);
  if (current.status >= 400) {
    return NextResponse.json(current.data, { status: current.status });
  }
  const dashboardId = snapshotId(current.data);
  if (!dashboardId) return fail('the dashboard snapshot did not include an id', 502);

  const revision = explicitRevision ?? snapshotRevision(current.data);
  if (revision === null) return fail('the dashboard snapshot did not include a revision', 502);

  let saved = await putLayout(dashboardId, layout, revision, request);
  // A concurrent layout edit beat us between GET and PUT: re-read once and
  // retry with the current revision (unless the caller pinned a revision).
  if (saved.status === 409 && explicitRevision === null) {
    const fresh = await getSnapshot(dashboardId, request);
    const freshRevision = snapshotRevision(fresh.data);
    if (fresh.status < 400 && freshRevision !== null) {
      saved = await putLayout(dashboardId, layout, freshRevision, request);
    }
  }

  if (saved.status < 400) {
    const isReset = segments[2] === 'reset';
    const templateId = typeof body.templateId === 'string' ? body.templateId.trim() : undefined;
    await recordSdkAudit(request, {
      action: isReset ? 'dashboard.reset' : 'dashboard.apply_template',
      summary: isReset ? 'Reset the Command Center board' : `Applied the ${templateId} template`,
      resourceType: 'dashboard',
      resourceId: dashboardId,
      detail: { templateId, market, revision: snapshotRevision(saved.data) ?? revision },
    });
  }
  return NextResponse.json(saved.data, { status: saved.status });
}

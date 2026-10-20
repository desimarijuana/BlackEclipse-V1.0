import { HARNESS_PY_URL, pythonRuntimeReachable } from '@/lib/harness/python-runtime';
import { runtimeProxyHeaders } from '@/lib/harness/runtime-identity';

export interface SdkAuditEntryInput {
  action: string;
  summary?: string;
  resourceType?: string;
  resourceId?: string;
  detail?: Record<string, unknown>;
}

/**
 * Record a front-door-owned SDK mutation (theme, app shell, dashboard template)
 * in the runtime's single append-only audit table. Best-effort: the mutation
 * already succeeded, so an unavailable runtime never turns success into failure.
 */
export async function recordSdkAudit(request: Request, entry: SdkAuditEntryInput): Promise<void> {
  try {
    if (!(await pythonRuntimeReachable())) return;
    const headers = await runtimeProxyHeaders(request, { json: true });
    const user = request.headers.get('x-eclipse-user');
    if (user) headers['X-Harness-User'] = user;
    await fetch(`${HARNESS_PY_URL}/sdk/audit`, {
      method: 'POST',
      headers,
      body: JSON.stringify(entry),
      signal: AbortSignal.timeout(5_000),
    });
  } catch {
    /* audit is best-effort; never surface a logging failure as a failed edit */
  }
}

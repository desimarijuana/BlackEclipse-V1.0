// ── Server-side run dispatch ─────────────────────────────────────────────────
// The ONE place a persisted workflow is turned into a runtime run — used by the
// interactive runs route, the schedule tick and the webhook trigger, so all
// three share the same trust boundary (IR loaded from JDDS, never from a caller)
// and the same test-run envelope.
//
// Server-only.

import { HARNESS_PY_URL, ensurePythonRuntime } from '@/lib/harness/python-runtime';
import { runtimeCallbackToken } from '@/lib/harness/runtime-auth';
import { runtimeIdentityHeaders } from '@/lib/harness/runtime-identity';
import { getWorkflow } from './server-store';

export interface StartRunResult {
  ok: boolean;
  status: number;
  run?: unknown;
  error?: string;
  detail?: unknown;
}

export async function startPersistedRun(options: {
  workflowId: string;
  version?: number | null;
  request?: Request;
  testRun?: boolean;
}): Promise<StartRunResult> {
  const healthy = await ensurePythonRuntime();
  if (!healthy) {
    return {
      ok: false,
      status: 503,
      error: 'The Python agent runtime is not available. Install the runtime: npm run setup:python',
    };
  }

  let workflow;
  try {
    workflow = await getWorkflow(options.workflowId, options.version ?? undefined);
  } catch (err) {
    return { ok: false, status: 500, error: err instanceof Error ? err.message : 'workflow could not be loaded' };
  }
  if (!workflow) return { ok: false, status: 404, error: 'Workflow not found' };

  const token = runtimeCallbackToken();
  const user = options.request?.headers.get('x-eclipse-user');
  const identity = options.request ? await runtimeIdentityHeaders(options.request) : {};
  try {
    const res = await fetch(`${HARNESS_PY_URL}/graphs/runs`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { 'X-Harness-Operator': token } : {}),
        ...identity,
        ...(user ? { 'X-Harness-User': user } : {}),
      },
      signal: AbortSignal.timeout(30_000),
      body: JSON.stringify({
        ir: workflow.ir,
        workflowVersion: workflow.version,
        // Phase 3/4: only test runs are reachable from the app. The runtime
        // enforces this independently of anything a caller sends.
        testRun: options.testRun ?? true,
        grantedCapabilities: [],
        allowNetwork: false,
        allowTrading: false,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      return {
        ok: false,
        status: res.status,
        error: (data as { detail?: { message?: string }; error?: string }).detail?.message ?? (data as { error?: string }).error ?? `Run rejected (${res.status})`,
        detail: (data as { detail?: unknown }).detail,
      };
    }
    return { ok: true, status: res.status, run: (data as { run?: unknown }).run };
  } catch (err) {
    return { ok: false, status: 502, error: err instanceof Error ? err.message : 'failed to start run' };
  }
}

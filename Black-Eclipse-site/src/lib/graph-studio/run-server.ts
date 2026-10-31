// ── Server-side run dispatch ─────────────────────────────────────────────────
// The ONE place a persisted workflow is turned into a runtime run — used by the
// interactive runs route, the schedule tick and the webhook trigger, so all
// three share the same trust boundary (IR loaded from JDDS, never from a caller)
// and the same test-run envelope.
//
// Server-only.

import { HARNESS_PY_URL, ensurePythonRuntime } from '@/lib/harness/python-runtime';
import { runtimeBaseUrl, runtimeCallbackToken } from '@/lib/harness/runtime-auth';
import { runtimeIdentityHeaders } from '@/lib/harness/runtime-identity';
import { getLLMConfig } from '@/lib/settings';
import { getWorkflow } from './server-store';
import {
  alignSubworkflowIds,
  alignWorkflowIdentity,
  collectSubworkflows,
} from './subworkflow-bundle';
import { authorizeGraphRun, type RunAuthorizationOptions } from './run-authorization';

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
  /** Omitted = a TEST run. An operator run grants only what the graph needs. */
  authorization?: RunAuthorizationOptions;
  /** One-off value the trigger emits as Start (a manual run or webhook body). */
  runInput?: unknown;
  /** Kept for existing callers; a test run is the default. */
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

  // The persisted JDDS row id is the ONE workflow identity a run is recorded
  // against. A stored IR keeps its own document id (`wf_…`), but run history,
  // schedules and subworkflow lookups all address the row id — so the runtime
  // receives it as the IR id (the document id is not a semantic input to
  // execution).
  const runtimeIr = alignWorkflowIdentity(workflow.ir, workflow.id);

  // The Python runtime cannot read JDDS. Resolve every PINNED subworkflow the
  // graph references (recursively, bounded) and send the IRs with the run.
  let subworkflows;
  try {
    const loaded = await collectSubworkflows(
      runtimeIr,
      async (subId, subVersion) => (await getWorkflow(subId, subVersion))?.ir ?? null,
      { rootKey: `${workflow.id}@${workflow.version}` },
    );
    subworkflows = alignSubworkflowIds(loaded);
  } catch (err) {
    return { ok: false, status: 400, error: err instanceof Error ? err.message : 'subworkflow could not be loaded' };
  }

  const authorized = authorizeGraphRun(runtimeIr, subworkflows, options.authorization ?? {});
  if (!authorized.ok) {
    return { ok: false, status: 400, error: authorized.error ?? 'Run is not authorized' };
  }

  // Only an agent node needs model credentials. They are resolved here from the
  // vault and sent to the runtime IN MEMORY; the runtime excludes them from the
  // durable Fabric job payload. A TEST run also needs them now: a model call is
  // not a world effect, and the runtime narrows the tool surface to read-only.
  let modelSettings: Record<string, unknown> | undefined;
  if (authorized.summary.requiredCapabilities.includes('agent.run')) {
    const llm = await getLLMConfig();
    if (!llm || llm.provider === 'mock') {
      return {
        ok: false,
        status: 400,
        error: 'This workflow uses an agent node, but no model provider is configured. Configure one in Settings.',
      };
    }
    modelSettings = {
      provider: llm.provider,
      baseUrl: llm.baseUrl,
      apiKey: llm.apiKey,
      model: llm.model,
      contextWindow: llm.contextWindow,
    };
  }

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
        ir: runtimeIr,
        workflowVersion: workflow.version,
        // A durable job may resume in a different process. The worker uses this
        // to re-resolve model credentials from the vault on demand; the key is
        // never written into the persisted job payload.
        callbackBaseUrl: runtimeBaseUrl(),
        subworkflows,
        // One-off trigger input for THIS run only; never persisted.
        ...(options.runInput !== undefined ? { runInput: options.runInput } : {}),
        // Computed from the registry + the persisted IR, never from a caller.
        ...authorized.authorization,
        ...(modelSettings ? { modelSettings } : {}),
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

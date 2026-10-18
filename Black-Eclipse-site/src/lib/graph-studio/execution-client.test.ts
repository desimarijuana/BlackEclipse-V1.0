import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  cancelGraphRun,
  getGraphRun,
  GraphRunApiError,
  isTerminal,
  startWorkflowRun,
} from './execution-client';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('execution client', () => {
  it('starts a run through the workflow runs route', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(jsonResponse({ run: { id: 'grun_1', status: 'running' } }, 201));
    const run = await startWorkflowRun('wf_1', 3);
    expect(run.id).toBe('grun_1');
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/workflows/wf_1/runs');
    expect(init?.method).toBe('POST');
    expect(JSON.parse(String(init?.body))).toEqual({ version: 3 });
  });

  it('surfaces the runtime message and plan from a rejected run', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse(
        { detail: { code: 'graph_not_executable', message: 'The graph has no terminal (output) node.', plan: { executable: false } } },
        400,
      ),
    );
    await expect(startWorkflowRun('wf_1')).rejects.toMatchObject({
      name: 'GraphRunApiError',
      status: 400,
      message: 'The graph has no terminal (output) node.',
    });
    await expect(startWorkflowRun('wf_1')).rejects.toBeInstanceOf(GraphRunApiError);
  });

  it('reads and cancels a run', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse({ run: { id: 'grun_2', status: 'running' } }))
      .mockResolvedValueOnce(jsonResponse({ run: { id: 'grun_2', status: 'cancelled' } }));
    expect((await getGraphRun('grun_2')).status).toBe('running');
    expect((await cancelGraphRun('grun_2')).status).toBe('cancelled');
    expect(fetchMock.mock.calls[1][0]).toBe('/api/graph-runs/grun_2/cancel');
    expect(fetchMock.mock.calls[1][1]?.method).toBe('POST');
  });

  it('knows terminal states', () => {
    expect(isTerminal('running')).toBe(false);
    expect(isTerminal('pending')).toBe(false);
    for (const status of ['succeeded', 'failed', 'cancelled'] as const) {
      expect(isTerminal(status)).toBe(true);
    }
  });
});

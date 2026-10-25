import { describe, expect, it } from 'vitest';
import type { GraphRunRecord, NodeRunRecord } from './execution-client';
import { buildRunSteps, stepIndexFor, summarizeRunSteps } from './run-debug';

function nodeRun(overrides: Partial<NodeRunRecord> & { nodeId: string }): NodeRunRecord {
  return {
    nodeType: 'transform.formula',
    label: overrides.nodeId,
    status: 'succeeded',
    layer: 0,
    attempt: 1,
    inputs: {},
    outputs: {},
    ...overrides,
  };
}

function run(nodeRuns: NodeRunRecord[]): GraphRunRecord {
  return {
    id: 'run_1',
    workflowId: 'wf_1',
    irVersion: 1,
    mode: 'research',
    testRun: true,
    status: 'failed',
    startedAt: '2026-10-25T10:00:00.000Z',
    nodeRuns,
    events: [
      { at: '2026-10-25T10:00:01.000Z', kind: 'node.started', nodeId: 'calc', message: 'started' },
      { at: '2026-10-25T10:00:02.000Z', kind: 'node.failed', nodeId: 'calc', message: 'boom' },
      { at: '2026-10-25T10:00:03.000Z', kind: 'run.failed', message: 'run failed' },
    ],
  };
}

describe('run step inspector', () => {
  it('orders steps by layer then start time', () => {
    const steps = buildRunSteps(run([
      nodeRun({ nodeId: 'out', layer: 2, startedAt: '2026-10-25T10:00:03.000Z' }),
      nodeRun({ nodeId: 'calc', layer: 1, startedAt: '2026-10-25T10:00:02.000Z', status: 'failed', error: 'boom' }),
      nodeRun({ nodeId: 'trig', layer: 0, startedAt: '2026-10-25T10:00:01.000Z' }),
    ]));
    expect(steps.map((step) => step.nodeId)).toEqual(['trig', 'calc', 'out']);
    expect(steps[1].events.map((event) => event.kind)).toEqual(['node.started', 'node.failed']);
    expect(steps[1].error).toBe('boom');
  });

  it('reports checkpoint availability and a summary', () => {
    const steps = buildRunSteps(run([
      nodeRun({ nodeId: 'a', resumable: true }),
      nodeRun({ nodeId: 'b', resumable: false, status: 'skipped' }),
      nodeRun({ nodeId: 'c', status: 'failed' }),
    ]));
    expect(steps[0].checkpointed).toBe(true);
    expect(steps[1].checkpointed).toBe(false);
    expect(summarizeRunSteps(steps)).toEqual({
      total: 3,
      succeeded: 1,
      failed: 1,
      skipped: 1,
      checkpointed: 1,
    });
    expect(stepIndexFor(steps, 'c')).toBe(2);
    expect(stepIndexFor(steps, 'missing')).toBe(-1);
  });

  it('attaches only that node\'s events, never a run-level event', () => {
    const steps = buildRunSteps(run([nodeRun({ nodeId: 'calc' })]));
    expect(steps[0].events.map((event) => event.kind)).toEqual(['node.started', 'node.failed']);
    expect(steps[0].events.every((event) => event.nodeId === 'calc')).toBe(true);
  });
});

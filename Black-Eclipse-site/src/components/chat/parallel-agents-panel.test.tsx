import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';

import { ParallelAgentsPanel } from './parallel-agents-panel';
import type { DelegationView } from '@/lib/agent/response-model';

const bestOf: DelegationView = {
  delegationId: 'dlg_1',
  aggregate: 'list',
  strategy: 'best_of',
  done: false,
  winner: 0,
  children: [
    {
      childIndex: 0, goal: 'Fix the flaky checkout test', approach: 'Add a retry',
      model: 'phi3', status: 'running', step: 4, maxSteps: 10,
      tokens: 900, costUsd: 0.12, agentId: 'eclipse-agent',
    },
    {
      childIndex: 1, goal: 'Fix the flaky checkout test', approach: 'Mock the payment API',
      status: 'completed', costUsd: null, agentId: 'eclipse-agent',
    },
    {
      childIndex: 2, goal: 'Fix the flaky checkout test', approach: 'Wait for the network',
      status: 'failed', reason: 'Could not reproduce it', agentId: 'code-agent',
    },
  ],
};

describe('ParallelAgentsPanel', () => {
  it('renders a best-of card with a winner, live rows and honest costs', () => {
    const html = renderToStaticMarkup(<ParallelAgentsPanel delegations={[bestOf]} />);
    expect(html).toContain('Best of 3');
    expect(html).toContain('2 of 3 done');
    expect(html).toContain('Best'); // the winner chip
    expect(html).toContain('phi3'); // the selected model names the row
    expect(html).toContain('Add a retry'); // the attempt's approach
    expect(html).toContain('Mock the payment API');
    expect(html).toContain('Could not reproduce it'); // the failed row's reason
    expect(html).toContain('$0.12');
    expect(html).toContain('—'); // an unpriced part is not "$0.00"
    expect(html).toContain('40%'); // step 4 of 10 — the runtime's own counters
  });

  it('reads as plain parallel work for a split fan-out', () => {
    const split: DelegationView = {
      ...bestOf,
      strategy: 'split',
      winner: undefined,
      children: bestOf.children.map((child) => ({ ...child, status: 'running' })),
    };
    const html = renderToStaticMarkup(<ParallelAgentsPanel delegations={[split]} />);
    expect(html).toContain('3 agents working');
    expect(html).not.toContain('Best of 3');
    expect(html).not.toContain('>Best<');
  });

  it('renders nothing when the turn did not delegate', () => {
    expect(renderToStaticMarkup(<ParallelAgentsPanel delegations={[]} />)).toBe('');
  });
});

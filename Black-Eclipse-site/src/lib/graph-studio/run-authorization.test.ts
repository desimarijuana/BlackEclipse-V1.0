import { describe, expect, it } from 'vitest';
import { createWorkflowIR } from './ir';
import { authorizeGraphRun, summarizeRunNeeds } from './run-authorization';
import type { WorkflowIR } from './types';

function graph(id: string, nodes: { id: string; type: string; config?: Record<string, unknown> }[]): WorkflowIR {
  return createWorkflowIR({
    id,
    nodes: nodes.map((node, index) => ({
      id: node.id,
      type: node.type,
      version: '1.0.0',
      config: node.config ?? {},
      layout: { x: index * 100, y: 0 },
    })),
    edges: [],
  });
}

const NETWORK_GRAPH = graph('wf_net', [
  { id: 'trig', type: 'trigger.manual' },
  { id: 'http', type: 'integration.http', config: { url: 'https://example.com' } },
  { id: 'out', type: 'output.result' },
]);

describe('run authorization', () => {
  it('defaults to a test run with no grants', () => {
    const result = authorizeGraphRun(NETWORK_GRAPH);
    expect(result.ok).toBe(true);
    expect(result.authorization).toEqual({
      testRun: true,
      grantedCapabilities: [],
      allowNetwork: false,
      allowTrading: false,
    });
  });

  it('an operator run requires explicit network confirmation', () => {
    const missing = authorizeGraphRun(NETWORK_GRAPH, [], { operator: true });
    expect(missing.ok).toBe(false);
    expect(missing.error).toContain('requires network access');
    const allowed = authorizeGraphRun(NETWORK_GRAPH, [], { operator: true, allowNetwork: true });
    expect(allowed.ok).toBe(true);
    expect(allowed.authorization.testRun).toBe(false);
    expect(allowed.authorization.allowNetwork).toBe(true);
    expect(allowed.authorization.grantedCapabilities).toContain('network.egress');
    expect(allowed.authorization.allowTrading).toBe(false);
  });

  it('refuses trading and external write nodes in an operator run', () => {
    const trading = graph('wf_trade', [
      { id: 'trig', type: 'trigger.manual' },
      { id: 'out', type: 'output.result' },
    ]);
    // The registry has no trading node yet; inject an unknown node to prove the
    // refusal path is explicit rather than silently accepting it.
    trading.nodes.push({
      id: 'trade', type: 'finance.order', version: '1.0.0', config: {}, layout: { x: 0, y: 0 },
    });
    const unknown = authorizeGraphRun(trading, [], { operator: true, allowNetwork: true });
    expect(unknown.ok).toBe(false);
    expect(unknown.error).toContain('Unknown node type');

    const write = graph('wf_write', [
      { id: 'trig', type: 'trigger.manual' },
      { id: 'video', type: 'video.render' },
      { id: 'out', type: 'output.result' },
    ]);
    const refused = authorizeGraphRun(write, [], { operator: true, allowNetwork: true });
    expect(refused.ok).toBe(false);
    expect(refused.error).toContain('write-effect');
  });

  it('treats web research nodes as network and local verification as a read', () => {
    const research = graph('wf_research', [
      { id: 'trig', type: 'trigger.manual' },
      { id: 'search', type: 'research.web_search', config: { query: 'inflation' } },
      { id: 'fetch', type: 'research.web_fetch', config: { url: 'https://example.com' } },
      { id: 'verify', type: 'research.claim_verify', config: { researchId: 'r1' } },
      { id: 'out', type: 'output.result' },
    ]);
    const summary = summarizeRunNeeds(research);
    expect(summary.requiresNetwork).toBe(true);
    expect(summary.networkNodes).toEqual(['Web search', 'Fetch page']);
    expect(summary.requiredCapabilities).toContain('network.egress');
    expect(summary.requiredCapabilities).toContain('research.read');

    const missing = authorizeGraphRun(research, [], { operator: true });
    expect(missing.ok).toBe(false);
    expect(missing.error).toContain('Web search');
    expect(authorizeGraphRun(research, [], { operator: true, allowNetwork: true }).ok).toBe(true);
  });

  it('collects capabilities from the root graph and subworkflows', () => {
    const child = graph('wf_child', [
      { id: 't', type: 'trigger.manual' },
      { id: 'm', type: 'finance.market_data' },
      { id: 'q', type: 'quant.backtest' },
      { id: 'o', type: 'output.result' },
    ]);
    const parent = graph('wf_parent', [
      { id: 't', type: 'trigger.manual' },
      { id: 'sub', type: 'flow.subworkflow', config: { workflowId: 'wf_child', version: 1 } },
      { id: 'o', type: 'output.result' },
    ]);
    const summary = summarizeRunNeeds(parent, [{ id: 'wf_child', version: 1, ir: child }]);
    expect(summary.requiredCapabilities).toContain('quant.compute');
    expect(summary.requiredCapabilities).toContain('market.read');
  });
});

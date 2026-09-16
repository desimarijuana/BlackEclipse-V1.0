import { describe, it, expect } from 'vitest';
import { buildGraph, neighboursOf } from './graph';
import type { RelationshipEdge } from './types';

function edge(overrides: Partial<RelationshipEdge> = {}): RelationshipEdge {
  return {
    edgeKey: Math.random().toString(36),
    fromKind: 'country', fromId: 'US', fromName: 'United States',
    toKind: 'commodity', toId: 'Crude Oil', toName: 'Crude Oil',
    relation: 'exposed_to',
    relationClass: 'OBSERVED',
    weight: 1,
    evidence: [],
    provenance: 'LIVE',
    ...overrides,
  };
}

describe('buildGraph', () => {
  it('creates one node per entity and one link per edge', () => {
    const graph = buildGraph([edge()]);
    expect(graph.nodes).toHaveLength(2);
    expect(graph.links).toHaveLength(1);
    expect(graph.nodes.find((n) => n.id === 'country:US')?.name).toBe('United States');
    expect(graph.nodes.find((n) => n.id === 'commodity:Crude Oil')?.kind).toBe('commodity');
  });

  it('increments degree and weight on both endpoints', () => {
    const graph = buildGraph([
      edge({ toId: 'Gold', toName: 'Gold' }),
      edge({ toId: 'Natural Gas', toName: 'Natural Gas' }),
    ]);
    const us = graph.nodes.find((n) => n.id === 'country:US')!;
    expect(us.degree).toBe(2);
    expect(us.weight).toBe(2);
  });

  it('collapses parallel edges between the same pair, summing weight', () => {
    const graph = buildGraph([
      edge({ relation: 'exposed_to' }),
      edge({ relation: 'trades_with' }),
    ]);
    expect(graph.links).toHaveLength(1);
    expect(graph.links[0].weight).toBe(2);
    expect(graph.links[0].relations.sort()).toEqual(['exposed_to', 'trades_with']);
  });

  it('collapses an undirected A→B / B→A pair into one link', () => {
    const graph = buildGraph([
      edge({ fromKind: 'country', fromId: 'US', fromName: 'United States', toKind: 'country', toId: 'CN', toName: 'China' }),
      edge({ fromKind: 'country', fromId: 'CN', fromName: 'China', toKind: 'country', toId: 'US', toName: 'United States' }),
    ]);
    expect(graph.links).toHaveLength(1);
    expect(graph.nodes).toHaveLength(2);
  });

  it('keeps the STRONGEST relation class when collapsing', () => {
    const graph = buildGraph([
      edge({ relationClass: 'INFERRED', relation: 'affected_by' }),
      edge({ relationClass: 'OBSERVED', relation: 'exposed_to' }),
    ]);
    expect(graph.links[0].relationClass).toBe('OBSERVED');
    expect(graph.links[0].relation).toBe('exposed_to');
  });

  it('never downgrades an observed link to inferred', () => {
    const graph = buildGraph([
      edge({ relationClass: 'OBSERVED' }),
      edge({ relationClass: 'INFERRED' }),
    ]);
    expect(graph.links[0].relationClass).toBe('OBSERVED');
  });

  it('filters edges below minWeight', () => {
    const graph = buildGraph([
      edge({ weight: 0.1, toId: 'Gold', toName: 'Gold' }),
      edge({ weight: 2, toId: 'Copper', toName: 'Copper' }),
    ], { minWeight: 1 });
    expect(graph.nodes.map((n) => n.id).sort()).toEqual(['commodity:Copper', 'country:US']);
  });

  it('filters by node kind', () => {
    const graph = buildGraph([
      edge(),
      edge({ fromKind: 'company', fromId: 'AAPL', fromName: 'Apple', toKind: 'sector', toId: 'Technology', toName: 'Technology' }),
    ], { kinds: ['country'] });
    expect(graph.nodes).toHaveLength(0);
  });

  it('drops self-loops', () => {
    const graph = buildGraph([edge({ toKind: 'country', toId: 'US', toName: 'United States' })]);
    expect(graph.links).toHaveLength(0);
  });

  it('bounds nodes and reports truncation honestly', () => {
    const edges = Array.from({ length: 20 }, (_, i) =>
      edge({ toKind: 'commodity', toId: `C${i}`, toName: `C${i}` }),
    );
    const graph = buildGraph(edges, { maxNodes: 5 });
    expect(graph.nodes).toHaveLength(5);
    expect(graph.totals.truncated).toBe(true);
    // No dangling links: every link endpoint must be a kept node.
    const ids = new Set(graph.nodes.map((n) => n.id));
    for (const l of graph.links) {
      expect(ids.has(l.source)).toBe(true);
      expect(ids.has(l.target)).toBe(true);
    }
  });

  it('does not truncate when under the node limit', () => {
    const graph = buildGraph([edge()], { maxNodes: 50 });
    expect(graph.totals.truncated).toBe(false);
  });

  it('caps a large uniform kind so it cannot crowd out others', () => {
    const companyEdges = Array.from({ length: 30 }, (_, i) =>
      edge({
        fromKind: 'company', fromId: `C${i}`, fromName: `Co ${i}`,
        toKind: 'sector', toId: `S${i}`, toName: `Sector ${i}`,
      }),
    );
    const graph = buildGraph(companyEdges, { maxPerKind: { company: 5 }, maxNodes: 200 });
    expect(graph.nodes.filter((n) => n.kind === 'company')).toHaveLength(5);
    // The other kind is not capped and keeps all its nodes.
    expect(graph.nodes.filter((n) => n.kind === 'sector')).toHaveLength(30);
  });

  it('leaves kinds without a cap untouched', () => {
    const graph = buildGraph(
      Array.from({ length: 20 }, (_, i) => edge({ toKind: 'commodity', toId: `C${i}`, toName: `C${i}` })),
      { maxPerKind: { company: 3 }, maxNodes: 200 },
    );
    expect(graph.nodes.filter((n) => n.kind === 'commodity')).toHaveLength(20);
  });

  it('attaches iso2 to country nodes via the resolver', () => {
    const graph = buildGraph([edge()], { iso2ForCountryId: (id) => (id === 'US' ? 'US' : undefined) });
    expect(graph.nodes.find((n) => n.id === 'country:US')?.iso2).toBe('US');
  });

  it('reports totals before truncation', () => {
    const edges = Array.from({ length: 10 }, (_, i) =>
      edge({ toKind: 'commodity', toId: `C${i}`, toName: `C${i}` }),
    );
    const graph = buildGraph(edges, { maxNodes: 3 });
    expect(graph.totals.edges).toBe(10);
    expect(graph.totals.nodes).toBe(11);
  });

  it('handles an empty edge list', () => {
    const graph = buildGraph([]);
    expect(graph.nodes).toEqual([]);
    expect(graph.links).toEqual([]);
    expect(graph.totals.edges).toBe(0);
  });

  it('sorts links strongest-first', () => {
    const graph = buildGraph([
      edge({ weight: 1, toId: 'Gold', toName: 'Gold' }),
      edge({ weight: 5, toId: 'Copper', toName: 'Copper' }),
    ]);
    expect(graph.links[0].weight).toBe(5);
  });
});

describe('neighboursOf', () => {
  it('returns a node with its incident links, strongest first', () => {
    const graph = buildGraph([
      edge({ weight: 1, toId: 'Gold', toName: 'Gold' }),
      edge({ weight: 4, toId: 'Copper', toName: 'Copper' }),
    ]);
    const { node, links } = neighboursOf(graph, 'country:US');
    expect(node?.id).toBe('country:US');
    expect(links).toHaveLength(2);
    expect(links[0].weight).toBe(4);
    expect(links[0].other?.id).toBe('commodity:Copper');
  });

  it('returns an empty neighbourhood for an unknown node', () => {
    const graph = buildGraph([edge()]);
    const { node, links } = neighboursOf(graph, 'country:ZZ');
    expect(node).toBeUndefined();
    expect(links).toEqual([]);
  });
});

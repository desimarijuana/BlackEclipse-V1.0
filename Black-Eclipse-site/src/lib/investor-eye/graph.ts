// ── Investor Eye — relationship graph builder (Phase 2.10, spec §41) ─────────
// Pure aggregation from stored `Relationship` edges into a render-ready
// node/link view. No database access and no ECharts here — callers pass edges
// in, the UI passes the result to the graph component.
//
// Design rules:
//   - Relational, not a graph DB (ADR-011). Edges are rows; this is a view.
//   - Every node/link keeps its `relationClass` so an inference is never
//     rendered as an observed fact.
//   - Bounded: `maxNodes` keeps the densest nodes and reports truncation
//     honestly rather than silently dropping edges.

import type {
  GraphLink, GraphNode, RelationClass, RelationshipEdge, RelationshipGraph,
} from './types';

/** Strongest-first ordering used when collapsing edges into one link. */
const CLASS_RANK: Record<RelationClass, number> = {
  OBSERVED: 3,
  HISTORICAL: 2,
  INFERRED: 1,
  'AI-INTERPRETED': 0,
};

function nodeId(kind: string, id: string): string {
  return `${kind}:${id}`;
}

export interface BuildGraphOptions {
  /** Max nodes kept (highest degree first). Default 200. */
  maxNodes?: number;
  /** Minimum edge weight to include. Default 0 (include all). */
  minWeight?: number;
  /** Keep only these node kinds (all kinds when omitted). */
  kinds?: string[];
  /**
   * Per-kind node cap. Without this, a large uniform population (e.g. hundreds
   * of company→sector edges) crowds out the geopolitical structure. The
   * highest-degree/weight nodes of each kind are kept.
   */
  maxPerKind?: Record<string, number>;
  /** ISO2 resolver so country nodes can offer a map pivot. */
  iso2ForCountryId?: (id: string) => string | undefined;
  provenance?: RelationshipGraph['provenance'];
}

/**
 * Aggregate edges into nodes + links.
 *
 * Multiple edges between the same ordered pair are collapsed into one link:
 * weight summed, `relations` collected, `relationClass` = strongest present.
 * Undirected duplicates (A→B and B→A) collapse together so the graph does not
 * render two overlapping lines.
 */
export function buildGraph(edges: RelationshipEdge[], options: BuildGraphOptions = {}): RelationshipGraph {
  const maxNodes = options.maxNodes ?? 200;
  const minWeight = options.minWeight ?? 0;
  const kindFilter = options.kinds && options.kinds.length > 0 ? new Set(options.kinds) : null;

  const nodes = new Map<string, GraphNode>();
  // Key an undirected pair so A→B and B→A merge, but keep direction of the
  // FIRST edge seen for the displayed source/target.
  const links = new Map<string, GraphLink & { directional: { source: string; target: string } }>();

  const ensureNode = (kind: string, id: string, name: string): GraphNode => {
    const key = nodeId(kind, id);
    let node = nodes.get(key);
    if (!node) {
      node = {
        id: key,
        kind,
        name,
        degree: 0,
        weight: 0,
        ...(kind === 'country' && options.iso2ForCountryId
          ? { iso2: options.iso2ForCountryId(id) }
          : {}),
      };
      nodes.set(key, node);
    }
    return node;
  };

  let edgeCount = 0;
  for (const edge of edges) {
    if (!Number.isFinite(edge.weight) || edge.weight < minWeight) continue;
    if (kindFilter && (!kindFilter.has(edge.fromKind) || !kindFilter.has(edge.toKind))) continue;

    const fromKey = nodeId(edge.fromKind, edge.fromId);
    const toKey = nodeId(edge.toKind, edge.toId);
    if (fromKey === toKey) continue; // no self-loops

    const fromNode = ensureNode(edge.fromKind, edge.fromId, edge.fromName);
    const toNode = ensureNode(edge.toKind, edge.toId, edge.toName);
    fromNode.degree += 1;
    toNode.degree += 1;
    fromNode.weight += edge.weight;
    toNode.weight += edge.weight;
    edgeCount += 1;

    const pairKey = [fromKey, toKey].sort().join('~');
    const existing = links.get(pairKey);
    if (!existing) {
      links.set(pairKey, {
        source: fromKey,
        target: toKey,
        relation: edge.relation,
        relationClass: edge.relationClass,
        weight: edge.weight,
        relations: [edge.relation],
        directional: { source: fromKey, target: toKey },
      });
      continue;
    }
    existing.weight += edge.weight;
    if (!existing.relations.includes(edge.relation)) existing.relations.push(edge.relation);
    if (CLASS_RANK[edge.relationClass] > CLASS_RANK[existing.relationClass]) {
      existing.relationClass = edge.relationClass;
      existing.relation = edge.relation;
    }
  }

  // Keep the densest nodes; drop links that reference a dropped node so the
  // graph never renders a dangling edge.
  const ranked = [...nodes.values()].sort(
    (a, b) => b.degree - a.degree || b.weight - a.weight || a.name.localeCompare(b.name),
  );

  // Apply the per-kind cap first (density-ordered), then the global cap.
  let eligible = ranked;
  if (options.maxPerKind) {
    const perKindCount = new Map<string, number>();
    eligible = ranked.filter((n) => {
      const cap = options.maxPerKind?.[n.kind];
      if (cap === undefined) return true;
      const used = perKindCount.get(n.kind) ?? 0;
      if (used >= cap) return false;
      perKindCount.set(n.kind, used + 1);
      return true;
    });
  }
  const truncated = eligible.length > maxNodes;
  const kept = new Set(eligible.slice(0, maxNodes).map((n) => n.id));

  const finalLinks: GraphLink[] = [...links.values()]
    .filter((l) => kept.has(l.source) && kept.has(l.target))
    .map(({ directional: _directional, ...link }) => link)
    .sort((a, b) => b.weight - a.weight);

  return {
    nodes: eligible.slice(0, maxNodes),
    links: finalLinks,
    totals: { edges: edgeCount, nodes: ranked.length, truncated },
    generatedAt: new Date().toISOString(),
    provenance: options.provenance ?? 'LIVE',
  };
}

/** Neighbours of a node, strongest first — used by the panel's focus mode. */
export function neighboursOf(graph: RelationshipGraph, nodeIdValue: string): {
  node: GraphNode | undefined;
  links: Array<GraphLink & { other: GraphNode | undefined }>;
} {
  const node = graph.nodes.find((n) => n.id === nodeIdValue);
  const links = graph.links
    .filter((l) => l.source === nodeIdValue || l.target === nodeIdValue)
    .map((l) => {
      const otherId = l.source === nodeIdValue ? l.target : l.source;
      return { ...l, other: graph.nodes.find((n) => n.id === otherId) };
    })
    .sort((a, b) => b.weight - a.weight);
  return { node, links };
}

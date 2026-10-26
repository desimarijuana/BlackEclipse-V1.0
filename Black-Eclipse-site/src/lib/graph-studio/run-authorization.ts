// ── Run authorization — the front door's least-privilege decision ───────────
// A graph run is either a TEST run (no world effects) or an explicitly
// authorized OPERATOR run. The IR is the authority for what the graph needs:
// capabilities and side-effect classes come from the registry, never from the
// caller. The caller only chooses whether to grant network; trading and external
// write effects are refused until the dedicated execution phases land.

import { getNodeDefinition } from './registry';
import type { SideEffectClass, WorkflowIR } from './types';
import type { SubworkflowBundleEntry } from './subworkflow-bundle';

export interface RunAuthorizationOptions {
  operator?: boolean;
  allowNetwork?: boolean;
  /** Explicit confirmation of the PAPER execution adapter. Live is never granted. */
  allowPaperTrading?: boolean;
  /** Explicit confirmation of a whitelisted LOCAL write (video render). */
  allowLocalWrite?: boolean;
}

export interface RunAuthorization {
  testRun: boolean;
  grantedCapabilities: string[];
  allowNetwork: boolean;
  allowTrading: boolean;
  allowWrite: boolean;
}

export interface RunAuthorizationSummary {
  requiredCapabilities: string[];
  networkNodes: string[];
  writeNodes: string[];
  writeNodeTypes: string[];
  tradingNodes: string[];
  requiresNetwork: boolean;
}

export interface RunAuthorizationResult {
  ok: boolean;
  authorization: RunAuthorization;
  summary: RunAuthorizationSummary;
  error?: string;
}

const SAFE: RunAuthorization = {
  testRun: true,
  grantedCapabilities: [],
  allowNetwork: false,
  allowTrading: false,
  allowWrite: false,
};

/** Inspect the graph + its subworkflow bundle and derive what it actually
 *  requires. Unknown node types are surfaced, not silently skipped. */
export function summarizeRunNeeds(
  ir: WorkflowIR,
  subworkflows: SubworkflowBundleEntry[] = [],
): RunAuthorizationSummary & { unknownNodes: string[] } {
  const capabilities = new Set<string>();
  const networkNodes: string[] = [];
  const writeNodes: string[] = [];
  const writeNodeTypes: string[] = [];
  const tradingNodes: string[] = [];
  const unknownNodes: string[] = [];

  const graphs = [ir, ...subworkflows.map((entry) => entry.ir)];
  for (const graph of graphs) {
    for (const node of graph.nodes) {
      const def = getNodeDefinition(node.type, node.version);
      if (!def) {
        unknownNodes.push(`${node.type}@${node.version}`);
        continue;
      }
      for (const cap of def.capabilities) capabilities.add(cap);
      const effects: SideEffectClass = def.sideEffects;
      if (effects === 'network') networkNodes.push(node.label ?? def.label);
      if (effects === 'write') {
        writeNodes.push(node.label ?? def.label);
        writeNodeTypes.push(def.type);
      }
      if (effects === 'trading') tradingNodes.push(node.label ?? def.label);
    }
  }

  const requiredCapabilities = [...capabilities].sort();
  return {
    requiredCapabilities,
    networkNodes,
    writeNodes,
    writeNodeTypes,
    tradingNodes,
    requiresNetwork: networkNodes.length > 0,
    unknownNodes,
  };
}

export function authorizeGraphRun(
  ir: WorkflowIR,
  subworkflows: SubworkflowBundleEntry[] = [],
  options: RunAuthorizationOptions = {},
): RunAuthorizationResult {
  const summary = summarizeRunNeeds(ir, subworkflows);
  const base = { ...SAFE, grantedCapabilities: summary.requiredCapabilities };

  if (!options.operator) {
    return { ok: true, authorization: SAFE, summary };
  }
  if (summary.unknownNodes.length > 0) {
    return {
      ok: false,
      authorization: base,
      summary,
      error: `Unknown node type(s): ${summary.unknownNodes.join(', ')}`,
    };
  }
  if (summary.tradingNodes.length > 0) {
    if (ir.settings.executionMode === 'live') {
      return {
        ok: false,
        authorization: base,
        summary,
        error: 'Live trading is not available in Graph Studio. Set the workflow mode to paper.',
      };
    }
    if (ir.settings.executionMode !== 'paper') {
      return {
        ok: false,
        authorization: base,
        summary,
        error: `Paper-trading nodes require the workflow's execution mode to be paper (${summary.tradingNodes.join(', ')}).`,
      };
    }
    if (!options.allowPaperTrading) {
      return {
        ok: false,
        authorization: base,
        summary,
        error: `This workflow contains paper-trading nodes (${summary.tradingNodes.join(', ')}); confirm paper trading to run it.`,
      };
    }
  }
  if (summary.writeNodes.length > 0) {
    const unsupported = summary.writeNodeTypes.filter((type) => type !== 'video.render');
    if (unsupported.length > 0) {
      return {
        ok: false,
        authorization: base,
        summary,
        error: `External write-effect nodes are not enabled in operator runs yet (${summary.writeNodes.join(', ')}).`,
      };
    }
    if (!options.allowLocalWrite) {
      return {
        ok: false,
        authorization: base,
        summary,
        error: `This workflow writes local render files (${summary.writeNodes.join(', ')}); confirm the local render to run it.`,
      };
    }
  }
  if (summary.requiresNetwork && !options.allowNetwork) {
    return {
      ok: false,
      authorization: base,
      summary,
      error: `This workflow requires network access (${summary.networkNodes.join(', ')}); confirm network access to run it.`,
    };
  }

  return {
    ok: true,
    authorization: {
      testRun: false,
      grantedCapabilities: summary.requiredCapabilities,
      allowNetwork: summary.requiresNetwork && Boolean(options.allowNetwork),
      allowTrading: summary.tradingNodes.length > 0 && Boolean(options.allowPaperTrading),
      allowWrite: summary.writeNodes.length > 0 && Boolean(options.allowLocalWrite),
    },
    summary,
  };
}

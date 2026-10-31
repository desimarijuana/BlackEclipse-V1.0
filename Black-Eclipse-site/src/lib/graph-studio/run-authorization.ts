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
  /** Named `file.write` scopes the operator confirmed. */
  allowWriteScopes?: string[];
  /** Explicit confirmation of LIVE broker execution. */
  allowLiveTrading?: boolean;
}

export interface RunAuthorization {
  testRun: boolean;
  grantedCapabilities: string[];
  allowNetwork: boolean;
  allowTrading: boolean;
  allowWrite: boolean;
  allowedWriteScopes: string[];
  /** Explicit operator confirmation for LIVE broker execution. */
  allowLiveTrading: boolean;
}

export interface RunAuthorizationSummary {
  requiredCapabilities: string[];
  /** Nodes that call a model provider (tokens, not a world effect). */
  modelNodes: string[];
  networkNodes: string[];
  writeNodes: string[];
  writeNodeTypes: string[];
  /** `file.write` scopes the graph needs, in stable order. */
  writeScopes: string[];
  tradingNodes: string[];
  requiresModel: boolean;
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
  allowedWriteScopes: [],
  allowLiveTrading: false,
};

/** Inspect the graph + its subworkflow bundle and derive what it actually
 *  requires. Unknown node types are surfaced, not silently skipped. */
export function summarizeRunNeeds(
  ir: WorkflowIR,
  subworkflows: SubworkflowBundleEntry[] = [],
): RunAuthorizationSummary & { unknownNodes: string[] } {
  const capabilities = new Set<string>();
  const modelNodes: string[] = [];
  const networkNodes: string[] = [];
  const writeNodes: string[] = [];
  const writeNodeTypes: string[] = [];
  const writeScopes = new Set<string>();
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
      if (effects === 'model') modelNodes.push(node.label ?? def.label);
      if (effects === 'network') networkNodes.push(node.label ?? def.label);
      if (effects === 'write') {
        writeNodes.push(node.label ?? def.label);
        writeNodeTypes.push(def.type);
        if (def.type === 'file.write') {
          writeScopes.add(String(node.config.scope || 'workspace').trim() || 'workspace');
        }
      }
      if (effects === 'trading') tradingNodes.push(node.label ?? def.label);
    }
  }

  const requiredCapabilities = [...capabilities].sort();
  return {
    requiredCapabilities,
    modelNodes,
    networkNodes,
    writeNodes,
    writeNodeTypes,
    writeScopes: [...writeScopes].sort(),
    tradingNodes,
    requiresModel: modelNodes.length > 0,
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
      const LIVE_NODE_TYPES = new Set([
        'trading.broker_order',
        'trading.broker_close',
        'trading.broker_modify',
        'trading.broker_cancel',
      ]);
      const paperOnly = ir.nodes.filter((node) => {
        const def = getNodeDefinition(node.type, node.version);
        return def?.sideEffects === 'trading' && !LIVE_NODE_TYPES.has(node.type);
      });
      if (paperOnly.length > 0) {
        return {
          ok: false,
          authorization: base,
          summary,
          error: `Paper-only trading nodes cannot run in live mode (${paperOnly.map((node) => node.type).join(', ')}).`,
        };
      }
      if (!options.allowLiveTrading) {
        return {
          ok: false,
          authorization: base,
          summary,
          error: `This workflow can place LIVE broker orders (${summary.tradingNodes.join(', ')}); confirm live trading to run it.`,
        };
      }
      // Live execution must be pinned: a connection, and a mandate for orders.
      const missing = ir.nodes
        .filter((node) => getNodeDefinition(node.type, node.version)?.sideEffects === 'trading')
        .filter((node) => {
          const config = node.config ?? {};
          if (!String(config.connectionId ?? '').trim()) return true;
          if (node.type === 'trading.broker_order' && !String(config.mandateId ?? '').trim()) return true;
          return false;
        });
      if (missing.length > 0) {
        return {
          ok: false,
          authorization: base,
          summary,
          error: 'Every live trading node needs a pinned connection; broker orders also need a live mandate.',
        };
      }
    } else {
      if (ir.settings.executionMode !== 'paper') {
        return {
          ok: false,
          authorization: base,
          summary,
          error: `Trading nodes require the workflow's execution mode to be paper or live (${summary.tradingNodes.join(', ')}).`,
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
  }
  if (summary.writeNodes.length > 0) {
    const unsupported = summary.writeNodeTypes.filter(
      (type) => type !== 'video.render' && type !== 'file.write',
    );
    if (unsupported.length > 0) {
      return {
        ok: false,
        authorization: base,
        summary,
        error: `External write-effect nodes are not enabled in operator runs yet (${summary.writeNodes.join(', ')}).`,
      };
    }
    if (summary.writeNodeTypes.includes('video.render') && !options.allowLocalWrite) {
      return {
        ok: false,
        authorization: base,
        summary,
        error: `This workflow writes local render files (${summary.writeNodes.join(', ')}); confirm the local render to run it.`,
      };
    }
    if (summary.writeScopes.length > 0) {
      const granted = new Set(options.allowWriteScopes ?? []);
      const missing = summary.writeScopes.filter((scope) => !granted.has(scope));
      if (missing.length > 0) {
        return {
          ok: false,
          authorization: base,
          summary,
          error: `This workflow writes to the ${missing.join(', ')} scope(s); confirm them to run it.`,
        };
      }
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
      allowTrading:
        ir.settings.executionMode === 'paper'
        && summary.tradingNodes.length > 0
        && Boolean(options.allowPaperTrading),
      allowWrite: summary.writeNodeTypes.includes('video.render') && Boolean(options.allowLocalWrite),
      allowedWriteScopes: summary.writeScopes.filter((scope) =>
        (options.allowWriteScopes ?? []).includes(scope),
      ),
      allowLiveTrading:
        ir.settings.executionMode === 'live'
        && summary.tradingNodes.length > 0
        && Boolean(options.allowLiveTrading),
    },
    summary,
  };
}

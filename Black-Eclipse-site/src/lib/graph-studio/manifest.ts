// ── Node registry manifest — the cross-language contract ────────────────────
// The editor registry (this package) and the Python runtime registry
// (`python/harness/graph_runtime/nodes.py`) are intentionally separate code,
// but they must describe the SAME node contracts. This module renders the TS
// registry into a plain, deterministic JSON document; `registry.manifest.json`
// is that document checked in, and the Python suite asserts its own registry
// matches it node for node.
//
// Change a node contract here -> run `npm run graph:manifest` -> both suites
// prove the runtime agrees. Never hand-edit the JSON.

import { listNodeDefinitions } from './registry';
import type { NodeDefinition, PortDef } from './types';

export interface ManifestPort {
  id: string;
  name: string;
  type: string;
  kind: 'data' | 'control';
  optional: boolean;
  nullable: boolean;
}

export interface ManifestConfigField {
  name: string;
  kind: 'string' | 'number' | 'boolean' | 'object' | 'array';
  default: unknown;
}

export interface ManifestNode {
  type: string;
  version: string;
  category: string;
  label: string;
  description: string;
  inputs: ManifestPort[];
  outputs: ManifestPort[];
  configFields: ManifestConfigField[];
  capabilities: string[];
  sideEffects: string;
  allowedModes: string[];
  terminal: boolean;
}

export interface NodeManifest {
  manifestVersion: 1;
  source: 'eclipse-workflow-ir';
  nodes: ManifestNode[];
}

function portOf(port: PortDef): ManifestPort {
  return {
    id: port.id,
    name: port.name,
    type: port.type,
    kind: port.kind ?? 'data',
    optional: Boolean(port.optional),
    nullable: Boolean(port.nullable),
  };
}

function configKind(value: unknown): ManifestConfigField['kind'] {
  if (typeof value === 'boolean') return 'boolean';
  if (typeof value === 'number') return 'number';
  if (Array.isArray(value)) return 'array';
  if (value && typeof value === 'object') return 'object';
  return 'string';
}

function configFieldsOf(definition: NodeDefinition): ManifestConfigField[] {
  const defaults = definition.defaultConfig();
  return Object.keys(defaults)
    .sort()
    .map((name) => ({ name, kind: configKind(defaults[name]), default: defaults[name] }));
}

function nodeOf(definition: NodeDefinition): ManifestNode {
  return {
    type: definition.type,
    version: definition.version,
    category: definition.category,
    label: definition.label,
    description: definition.description,
    inputs: definition.inputs.map(portOf),
    outputs: definition.outputs.map(portOf),
    configFields: configFieldsOf(definition),
    capabilities: [...definition.capabilities].sort(),
    sideEffects: definition.sideEffects,
    allowedModes: [...definition.allowedModes].sort(),
    terminal: Boolean(definition.terminal),
  };
}

/** Build the deterministic manifest. */
export function buildNodeManifest(): NodeManifest {
  const nodes = listNodeDefinitions()
    .map(nodeOf)
    .sort((a, b) => `${a.type}@${a.version}`.localeCompare(`${b.type}@${b.version}`));
  return { manifestVersion: 1, source: 'eclipse-workflow-ir', nodes };
}

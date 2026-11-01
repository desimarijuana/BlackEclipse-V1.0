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

export interface ManifestConfigConstraints {
  maxLength?: number;
  enum?: string[];
  min?: number;
  max?: number;
  integer?: boolean;
}

export interface ManifestConfigField {
  name: string;
  kind: 'string' | 'number' | 'boolean' | 'object' | 'array';
  default: unknown;
  /** Bounds the runtime also enforces. Absent means "unconstrained". */
  constraints?: ManifestConfigConstraints;
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

/**
 * Read the declared bounds out of a zod field.
 *
 * The manifest's job is to let the Python suite prove it enforces the SAME
 * limits the editor shows — comparing field names alone let a `max(200)` and a
 * `max_length=4_000` disagree silently. `.def` is zod's public introspection
 * surface, so this stays a pure read (no schema duplication).
 */
function constraintsOf(schema: unknown): ManifestConfigConstraints | undefined {
  type Introspectable = {
    def?: { type?: string; innerType?: unknown };
    maxLength?: unknown;
    options?: unknown;
    minValue?: unknown;
    maxValue?: unknown;
    isInt?: unknown;
  };
  let current = schema as Introspectable | undefined;
  // Unwrap `.default()` / `.optional()` / `.nullable()` wrappers.
  while (current?.def && ['default', 'optional', 'nullable', 'readonly'].includes(current.def.type ?? '')) {
    current = current.def.innerType as Introspectable | undefined;
  }
  const type = current?.def?.type;
  if (!current || !type) return undefined;

  // zod 4 exposes the bounds on the schema itself (`maxLength`, `minValue`…)
  // and keeps only the kind on `.def`.
  const constraints: ManifestConfigConstraints = {};
  if (type === 'string' && typeof current.maxLength === 'number') {
    constraints.maxLength = current.maxLength;
  }
  if (type === 'enum' && Array.isArray(current.options)) {
    constraints.enum = (current.options as unknown[]).map((option) => String(option));
  }
  if (type === 'number') {
    if (Number.isFinite(current.minValue)) constraints.min = current.minValue as number;
    if (Number.isFinite(current.maxValue)) constraints.max = current.maxValue as number;
    if (current.isInt === true) constraints.integer = true;
  }
  return Object.keys(constraints).length > 0 ? constraints : undefined;
}

function configFieldsOf(definition: NodeDefinition): ManifestConfigField[] {
  const defaults = definition.defaultConfig();
  const shape = (definition.configSchema as { shape?: Record<string, unknown> } | undefined)?.shape ?? {};
  return Object.keys(defaults)
    .sort()
    .map((name) => {
      const field: ManifestConfigField = { name, kind: configKind(defaults[name]), default: defaults[name] };
      const constraints = constraintsOf(shape[name]);
      if (constraints) field.constraints = constraints;
      return field;
    });
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

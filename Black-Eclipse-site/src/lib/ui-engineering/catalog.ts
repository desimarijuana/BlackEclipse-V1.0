// ── UI Component Catalog ─────────────────────────────────────────────────────
// The authoritative, queryable description of every UI component the agent may
// compose. It is a PURE layer: it never imports React or the live widget
// registry. Hosts adapt their existing registry (WidgetDefinition) into
// `UiComponentSpec`s via `adaptWidgetDefinition`, so there is exactly one
// source of truth for what a component is and how it may be configured — the
// catalog does not fork the component library, it describes it.
//
// This is the Phase-2 backbone: the agent discovers components and their
// configuration schema here instead of hallucinating ids or config fields.

import type { WidgetConfigField, WidgetDefinition } from '@/lib/workspace/widget-def';
import type { WorkspaceZone } from '@/lib/workspace/types';

export type OwnershipKind = 'core' | 'plugin' | 'user';
export type ComponentAvailability = 'available' | 'unavailable';
export type ConfigFieldKind = WidgetConfigField['type'];

/** A single declarative configuration field of a component. */
export interface ComponentConfigFieldSpec {
  key: string;
  label: string;
  kind: ConfigFieldKind;
  options?: { value: string; label: string }[];
  required: boolean;
  default?: unknown;
  min?: number;
  max?: number;
  step?: number;
  placeholder?: string;
}

export interface ComponentLayoutSpec {
  sizes: string[];
  minHeight?: number;
  defaultHeight?: number;
  resizable: boolean;
  zones: WorkspaceZone[];
}

/** Everything the agent needs to know about one component. */
export interface UiComponentSpec {
  /** Stable registry id — persisted in blueprints. */
  id: string;
  /** Component contract version (independent of the host app version). */
  version: string;
  displayName: string;
  description: string;
  category: string;
  icon: string;
  tags: string[];
  configSchema: ComponentConfigFieldSpec[];
  defaultConfig: Record<string, unknown>;
  dataSources: string[];
  actions: string[];
  layout: ComponentLayoutSpec;
  availability: ComponentAvailability;
  owner: OwnershipKind;
  pluginId?: string;
}

export const COMPONENT_ACTIONS = [
  'remove',
  'move',
  'resize',
  'reorder',
  'configure',
  'duplicate',
  'hide',
] as const;

export interface ConfigIssue {
  path: string;
  message: string;
  severity: 'error' | 'warning';
}

export interface ConfigValidationResult {
  ok: boolean;
  issues: ConfigIssue[];
  config: Record<string, unknown>;
}

export interface CatalogQuery {
  text?: string;
  category?: string;
  dataSource?: string;
  owner?: OwnershipKind;
  availability?: ComponentAvailability;
  limit?: number;
}

function tokenize(value: string): string[] {
  return value
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter(t => t.length > 0);
}

/** Adapt one existing host widget definition into a catalog spec. */
export function adaptWidgetDefinition(
  def: WidgetDefinition,
  opts: { version?: string; owner?: OwnershipKind; pluginId?: string; availability?: ComponentAvailability; tags?: string[] } = {},
): UiComponentSpec {
  const configSchema: ComponentConfigFieldSpec[] = (def.configFields ?? []).map(field => ({
    key: field.key,
    label: field.label,
    kind: field.type,
    options: field.options,
    required: false,
    default: field.default,
    min: field.min,
    max: field.max,
    step: field.step,
    placeholder: field.placeholder,
  }));

  return {
    id: def.id,
    version: opts.version ?? '1.0.0',
    displayName: def.label,
    description: def.desc,
    category: def.category,
    icon: def.icon,
    tags: opts.tags ?? tokenize(`${def.label} ${def.desc} ${def.category}`),
    configSchema,
    defaultConfig: { ...(def.defaultConfig ?? {}) },
    dataSources: [...(def.catalogDataSources ?? def.dataDeps ?? [])],
    actions: [...COMPONENT_ACTIONS],
    layout: {
      sizes: [...def.sizes],
      minHeight: def.minHeight,
      defaultHeight: def.defaultHeight,
      resizable: true,
      zones: ['left', 'main', 'right'],
    },
    availability: opts.availability ?? 'available',
    owner: opts.owner ?? 'core',
    pluginId: opts.pluginId,
  };
}

function numberFieldIssue(path: string, spec: ComponentConfigFieldSpec, value: unknown): ConfigIssue | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return { path, message: `expected a number for "${spec.key}"`, severity: 'error' };
  }
  if (spec.min !== undefined && value < spec.min) {
    return { path, message: `"${spec.key}" is below its minimum of ${spec.min}`, severity: 'error' };
  }
  if (spec.max !== undefined && value > spec.max) {
    return { path, message: `"${spec.key}" is above its maximum of ${spec.max}`, severity: 'error' };
  }
  return null;
}

/**
 * Validate a component configuration against its declared schema. Unknown keys
 * are warnings (widgets may accept dynamic config), but wrong types and missing
 * required fields are hard errors so an invalid configuration is rejected BEFORE
 * it renders.
 */
export function validateComponentConfig(
  spec: UiComponentSpec,
  config: Record<string, unknown> | undefined,
): ConfigValidationResult {
  const issues: ConfigIssue[] = [];
  const value = config ?? {};
  const byKey = new Map(spec.configSchema.map(f => [f.key, f]));

  for (const [key, raw] of Object.entries(value)) {
    const field = byKey.get(key);
    if (!field) {
      issues.push({ path: key, message: `unknown configuration key "${key}"`, severity: 'warning' });
      continue;
    }
    switch (field.kind) {
      case 'number': {
        const issue = numberFieldIssue(key, field, raw);
        if (issue) issues.push(issue);
        break;
      }
      case 'boolean':
        if (typeof raw !== 'boolean') issues.push({ path: key, message: `expected a boolean for "${key}"`, severity: 'error' });
        break;
      case 'symbols':
        if (!Array.isArray(raw) || raw.some(v => typeof v !== 'string')) {
          issues.push({ path: key, message: `expected a string array for "${key}"`, severity: 'error' });
        }
        break;
      case 'select':
        if (typeof raw !== 'string' || (field.options && !field.options.some(o => o.value === raw))) {
          issues.push({ path: key, message: `"${key}" is not one of the allowed options`, severity: 'error' });
        }
        break;
      default:
        if (typeof raw !== 'string') issues.push({ path: key, message: `expected a string for "${key}"`, severity: 'error' });
    }
  }

  for (const field of spec.configSchema) {
    if (field.required && (value[field.key] === undefined || value[field.key] === null)) {
      issues.push({ path: field.key, message: `missing required configuration "${field.key}"`, severity: 'error' });
    }
  }

  return { ok: issues.every(i => i.severity !== 'error'), issues, config: { ...value } };
}

/** In-process registry of component specs keyed by stable id. */
export class ComponentCatalog {
  private readonly specs = new Map<string, UiComponentSpec>();

  constructor(specs: Iterable<UiComponentSpec> = []) {
    for (const spec of specs) this.register(spec);
  }

  register(spec: UiComponentSpec, opts: { replace?: boolean } = {}): void {
    if (!spec.id) throw new Error('component id is required');
    if (this.specs.has(spec.id) && !opts.replace) {
      throw new Error(`component "${spec.id}" is already registered`);
    }
    this.specs.set(spec.id, spec);
  }

  has(id: string): boolean {
    return this.specs.has(id);
  }

  get(id: string): UiComponentSpec | undefined {
    return this.specs.get(id);
  }

  list(): UiComponentSpec[] {
    return [...this.specs.values()].sort((a, b) => a.id.localeCompare(b.id));
  }

  categories(): string[] {
    return [...new Set(this.list().map(s => s.category))].sort();
  }

  dataSources(): string[] {
    return [...new Set(this.list().flatMap(s => s.dataSources))].sort();
  }

  search(query: CatalogQuery = {}): UiComponentSpec[] {
    const tokens = query.text ? tokenize(query.text) : [];
    const scored: { spec: UiComponentSpec; score: number }[] = [];

    for (const spec of this.list()) {
      if (query.category && spec.category !== query.category) continue;
      if (query.owner && spec.owner !== query.owner) continue;
      if (query.availability && spec.availability !== query.availability) continue;
      if (query.dataSource && !spec.dataSources.includes(query.dataSource)) continue;

      let score = 0;
      if (tokens.length > 0) {
        const haystack = [spec.id, spec.displayName, spec.description, spec.category, ...spec.tags].map(s => s.toLowerCase());
        for (const token of tokens) {
          if (spec.id.toLowerCase() === token) score += 8;
          else if (haystack.some(h => h === token)) score += 4;
          else if (haystack.some(h => h.includes(token))) score += 2;
        }
        if (score === 0) continue;
      }
      scored.push({ spec, score });
    }

    scored.sort((a, b) => b.score - a.score || a.spec.id.localeCompare(b.spec.id));
    const results = scored.map(s => s.spec);
    return typeof query.limit === 'number' ? results.slice(0, Math.max(0, query.limit)) : results;
  }

  validateConfig(id: string, config: Record<string, unknown> | undefined): ConfigValidationResult {
    const spec = this.specs.get(id);
    if (!spec) {
      return { ok: false, issues: [{ path: id, message: `unknown component "${id}"`, severity: 'error' }], config: config ?? {} };
    }
    return validateComponentConfig(spec, config);
  }
}

// ── Declarative UI Blueprint ─────────────────────────────────────────────────
// A blueprint is the durable, versioned description of a page/workspace. It
// wraps the existing workspace `WorkspaceLayout` tree (so the proven layout
// engine renders it) with identity, ownership, scope and revision metadata.
//
// Validation is STRICT and truthful: unlike the lenient storage reader it
// reports every problem (unknown component, duplicate instance, bad config)
// instead of silently dropping entries, so the agent is told the real reason a
// blueprint is rejected before anything renders. No blueprint field ever
// executes code — configuration is data validated against the catalog.

import { WORKSPACE_VERSION, type WorkspaceLayout } from '@/lib/workspace/types';
import type { ComponentCatalog, ConfigIssue, OwnershipKind } from './catalog';

export const BLUEPRINT_SCHEMA_VERSION = 1 as const;

export type BlueprintKind = 'page' | 'workspace';
export type BlueprintScope = 'personal' | 'shared';

export interface BlueprintOwner {
  kind: OwnershipKind;
  /** Actor/plugin id that owns the blueprint (e.g. 'operator', 'hello-world'). */
  id: string;
}

export interface UiBlueprint {
  schemaVersion: number;
  id: string;
  title: string;
  description?: string;
  kind: BlueprintKind;
  owner: BlueprintOwner;
  scope: BlueprintScope;
  /** Route/nav path when the blueprint is a page. */
  path?: string;
  tags?: string[];
  layout: WorkspaceLayout;
  revision: number;
  createdAt: string;
  updatedAt: string;
}

export interface BlueprintValidation {
  ok: boolean;
  issues: ConfigIssue[];
  blueprint?: UiBlueprint;
}

export interface CreateBlueprintInit {
  id?: string;
  title: string;
  description?: string;
  kind?: BlueprintKind;
  owner?: BlueprintOwner;
  scope?: BlueprintScope;
  path?: string;
  tags?: string[];
  layout: WorkspaceLayout;
  now?: string;
}

let counter = 0;
export function newBlueprintId(): string {
  counter += 1;
  return `bp-${Date.now().toString(36)}-${counter.toString(36)}${Math.random().toString(36).slice(2, 6)}`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0;
}

/** Validate the layout tree structurally and against the catalog. */
export function validateLayout(
  raw: unknown,
  catalog?: ComponentCatalog,
): { issues: ConfigIssue[]; layout?: WorkspaceLayout } {
  const issues: ConfigIssue[] = [];
  if (!isRecord(raw)) {
    return { issues: [{ path: 'layout', message: 'layout must be an object', severity: 'error' }] };
  }
  if (!Array.isArray(raw.sections)) {
    return { issues: [{ path: 'layout.sections', message: 'layout.sections must be an array', severity: 'error' }] };
  }

  const seenInstances = new Set<string>();
  const seenSections = new Set<string>();
  const seenColumns = new Set<string>();

  const sections = (raw.sections as unknown[]).map((sectionRaw, si) => {
    const sPath = `layout.sections[${si}]`;
    const section: WorkspaceLayout['sections'][number] = { id: '', columns: [] };
    if (!isRecord(sectionRaw)) {
      issues.push({ path: sPath, message: 'section must be an object', severity: 'error' });
      return section;
    }
    section.id = isNonEmptyString(sectionRaw.id) ? sectionRaw.id : '';
    if (!section.id) issues.push({ path: `${sPath}.id`, message: 'section id is required', severity: 'error' });
    else if (seenSections.has(section.id)) issues.push({ path: `${sPath}.id`, message: `duplicate section id "${section.id}"`, severity: 'error' });
    else seenSections.add(section.id);

    if (sectionRaw.zone === 'left' || sectionRaw.zone === 'main' || sectionRaw.zone === 'right') {
      section.zone = sectionRaw.zone;
    }

    const columnsRaw = Array.isArray(sectionRaw.columns) ? sectionRaw.columns : [];
    if (!Array.isArray(sectionRaw.columns)) {
      issues.push({ path: `${sPath}.columns`, message: 'section.columns must be an array', severity: 'error' });
    }
    if (columnsRaw.length > 4) {
      issues.push({ path: `${sPath}.columns`, message: 'a section may not have more than 4 columns', severity: 'error' });
    }

    section.columns = columnsRaw.map((columnRaw, ci) => {
      const cPath = `${sPath}.columns[${ci}]`;
      const column: WorkspaceLayout['sections'][number]['columns'][number] = { id: '', weight: 3, widgets: [] };
      if (!isRecord(columnRaw)) {
        issues.push({ path: cPath, message: 'column must be an object', severity: 'error' });
        return column;
      }
      column.id = isNonEmptyString(columnRaw.id) ? columnRaw.id : '';
      if (!column.id) issues.push({ path: `${cPath}.id`, message: 'column id is required', severity: 'error' });
      else if (seenColumns.has(column.id)) issues.push({ path: `${cPath}.id`, message: `duplicate column id "${column.id}"`, severity: 'error' });
      else seenColumns.add(column.id);

      const weight = columnRaw.weight;
      if (typeof weight !== 'number' || !Number.isFinite(weight) || weight <= 0) {
        issues.push({ path: `${cPath}.weight`, message: 'column weight must be a positive number', severity: 'error' });
      } else {
        column.weight = weight;
      }

      const widgetsRaw = Array.isArray(columnRaw.widgets) ? columnRaw.widgets : [];
      if (!Array.isArray(columnRaw.widgets)) {
        issues.push({ path: `${cPath}.widgets`, message: 'column.widgets must be an array', severity: 'error' });
      }
      column.widgets = widgetsRaw.map((widgetRaw, wi) => {
        const wPath = `${cPath}.widgets[${wi}]`;
        const placement: WorkspaceLayout['sections'][number]['columns'][number]['widgets'][number] = {
          id: '',
          widgetId: '',
          height: null,
        };
        if (!isRecord(widgetRaw)) {
          issues.push({ path: wPath, message: 'widget placement must be an object', severity: 'error' });
          return placement;
        }
        placement.id = isNonEmptyString(widgetRaw.id) ? widgetRaw.id : '';
        if (!placement.id) issues.push({ path: `${wPath}.id`, message: 'instance id is required', severity: 'error' });
        else if (seenInstances.has(placement.id)) issues.push({ path: `${wPath}.id`, message: `duplicate instance id "${placement.id}"`, severity: 'error' });
        else seenInstances.add(placement.id);

        placement.widgetId = isNonEmptyString(widgetRaw.widgetId) ? widgetRaw.widgetId : '';
        if (!placement.widgetId) {
          issues.push({ path: `${wPath}.widgetId`, message: 'widgetId is required', severity: 'error' });
        } else if (catalog && !catalog.has(placement.widgetId)) {
          issues.push({ path: `${wPath}.widgetId`, message: `unknown component "${placement.widgetId}"`, severity: 'error' });
        }

        if (typeof widgetRaw.height === 'number' && Number.isFinite(widgetRaw.height)) placement.height = widgetRaw.height;
        if (typeof widgetRaw.defaultHeight === 'number' && Number.isFinite(widgetRaw.defaultHeight)) placement.defaultHeight = widgetRaw.defaultHeight;
        if (typeof widgetRaw.minHeight === 'number' && Number.isFinite(widgetRaw.minHeight)) placement.minHeight = widgetRaw.minHeight;
        if (widgetRaw.hidden === true) placement.hidden = true;
        if (isRecord(widgetRaw.config)) placement.config = { ...widgetRaw.config };

        if (catalog && placement.widgetId && placement.config) {
          const result = catalog.validateConfig(placement.widgetId, placement.config);
          for (const issue of result.issues) issues.push({ ...issue, path: `${wPath}.config.${issue.path}` });
        }
        return placement;
      });
      return column;
    });
    return section;
  });

  return {
    issues,
    layout: { version: WORKSPACE_VERSION, sections },
  };
}

/** Validate a full blueprint payload. Returns the cleaned blueprint only when valid. */
export function validateBlueprint(raw: unknown, catalog?: ComponentCatalog): BlueprintValidation {
  const issues: ConfigIssue[] = [];
  if (!isRecord(raw)) return { ok: false, issues: [{ path: '', message: 'blueprint must be an object', severity: 'error' }] };

  const schemaVersion = raw.schemaVersion;
  if (typeof schemaVersion !== 'number' || schemaVersion < 1) {
    issues.push({ path: 'schemaVersion', message: 'schemaVersion must be a positive integer', severity: 'error' });
  } else if (schemaVersion > BLUEPRINT_SCHEMA_VERSION) {
    issues.push({ path: 'schemaVersion', message: `blueprint schema ${schemaVersion} is newer than supported ${BLUEPRINT_SCHEMA_VERSION}`, severity: 'error' });
  }

  const id = isNonEmptyString(raw.id) ? raw.id : '';
  if (!id) issues.push({ path: 'id', message: 'blueprint id is required', severity: 'error' });

  const title = isNonEmptyString(raw.title) ? raw.title : '';
  if (!title) issues.push({ path: 'title', message: 'blueprint title is required', severity: 'error' });

  const kind: BlueprintKind = raw.kind === 'workspace' ? 'workspace' : 'page';
  const scope: BlueprintScope = raw.scope === 'shared' ? 'shared' : 'personal';

  const ownerRaw = isRecord(raw.owner) ? raw.owner : {};
  const owner: BlueprintOwner = {
    kind: ownerRaw.kind === 'plugin' || ownerRaw.kind === 'user' ? ownerRaw.kind : 'core',
    id: isNonEmptyString(ownerRaw.id) ? ownerRaw.id : 'operator',
  };

  const revision = typeof raw.revision === 'number' && Number.isInteger(raw.revision) && raw.revision >= 1 ? raw.revision : 1;
  const now = new Date().toISOString();
  const createdAt = isNonEmptyString(raw.createdAt) ? raw.createdAt : now;
  const updatedAt = isNonEmptyString(raw.updatedAt) ? raw.updatedAt : now;

  const layoutResult = validateLayout(raw.layout, catalog);
  issues.push(...layoutResult.issues);

  if (issues.some(i => i.severity === 'error') || !layoutResult.layout) {
    return { ok: false, issues };
  }

  const blueprint: UiBlueprint = {
    schemaVersion: BLUEPRINT_SCHEMA_VERSION,
    id,
    title,
    kind,
    owner,
    scope,
    layout: layoutResult.layout,
    revision,
    createdAt,
    updatedAt,
    ...(isNonEmptyString(raw.description) ? { description: raw.description } : {}),
    ...(isNonEmptyString(raw.path) ? { path: raw.path } : {}),
    ...(Array.isArray(raw.tags) ? { tags: raw.tags.filter(isNonEmptyString) } : {}),
  };
  return { ok: true, issues, blueprint };
}

export function createBlueprint(init: CreateBlueprintInit): UiBlueprint {
  const now = init.now ?? new Date().toISOString();
  return {
    schemaVersion: BLUEPRINT_SCHEMA_VERSION,
    id: init.id ?? newBlueprintId(),
    title: init.title,
    kind: init.kind ?? 'page',
    owner: init.owner ?? { kind: 'user', id: 'operator' },
    scope: init.scope ?? 'personal',
    layout: init.layout,
    revision: 1,
    createdAt: now,
    updatedAt: now,
    ...(init.description !== undefined ? { description: init.description } : {}),
    ...(init.path !== undefined ? { path: init.path } : {}),
    ...(init.tags !== undefined ? { tags: init.tags } : {}),
  };
}

/** Return a copy of the blueprint with a bumped revision and fresh timestamp. */
export function touchBlueprint(blueprint: UiBlueprint, now?: string): UiBlueprint {
  return { ...blueprint, revision: blueprint.revision + 1, updatedAt: now ?? new Date().toISOString() };
}

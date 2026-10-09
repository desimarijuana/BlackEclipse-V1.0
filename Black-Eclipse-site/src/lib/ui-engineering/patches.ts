// ── Blueprint mutation engine ────────────────────────────────────────────────
// A closed set of atomic, validated operations over a blueprint. Every op is
// checked against the live catalog and current layout BEFORE any mutation, and
// the whole set is applied in a single Immer transaction, so a batch either
// fully applies (bumping the revision once) or leaves the blueprint untouched.
// The layout math itself is delegated to the existing workspace ops — this file
// adds validation, identity control and revision semantics, not a second engine.

import { produce } from 'immer';
import type { Draft } from 'immer';
import { newId } from '@/lib/workspace/types';
import type { DropTarget, WidgetPlacement, WorkspaceLayout, WorkspaceZone } from '@/lib/workspace/types';
import {
  addWidget,
  duplicateWidget,
  locate,
  moveWidget,
  removeSection,
  removeWidget,
  setColumnCount,
  setColumnWeight,
  setWidgetConfig,
  setWidgetHeight,
} from '@/lib/workspace/ops';
import type { ComponentCatalog, ConfigIssue } from './catalog';
import { touchBlueprint, type UiBlueprint } from './blueprint';

export type BlueprintOp =
  | { op: 'add_widget'; componentId: string; instanceId?: string; target?: DropTarget; config?: Record<string, unknown>; zone?: WorkspaceZone; height?: number | null }
  | { op: 'remove_widget'; instanceId: string }
  | { op: 'move_widget'; instanceId: string; target: DropTarget }
  | { op: 'reorder_widget'; instanceId: string; toIndex: number }
  | { op: 'resize_widget'; instanceId: string; height: number | null }
  | { op: 'update_config'; instanceId: string; patch: Record<string, unknown> }
  | { op: 'duplicate_widget'; instanceId: string }
  | { op: 'set_column_count'; sectionId: string; count: number }
  | { op: 'set_column_weight'; columnId: string; weight: number }
  | { op: 'remove_section'; sectionId: string }
  | { op: 'update_meta'; title?: string; description?: string; path?: string; tags?: string[] };

export interface ApplyBlueprintOpsOptions {
  catalog?: ComponentCatalog;
  now?: string;
}

export interface ApplyBlueprintOpsResult {
  ok: boolean;
  blueprint: UiBlueprint;
  issues: ConfigIssue[];
  applied: number;
}

function sectionExists(layout: WorkspaceLayout, sectionId: string): boolean {
  return layout.sections.some(s => s.id === sectionId);
}

function columnExists(layout: WorkspaceLayout, sectionId: string, columnId: string): boolean {
  const section = layout.sections.find(s => s.id === sectionId);
  return Boolean(section && section.columns.some(c => c.id === columnId));
}

function validateOp(op: BlueprintOp, blueprint: UiBlueprint, catalog?: ComponentCatalog): ConfigIssue[] {
  const issues: ConfigIssue[] = [];
  const layout = blueprint.layout;

  switch (op.op) {
    case 'add_widget': {
      if (!op.componentId) issues.push({ path: 'componentId', message: 'componentId is required', severity: 'error' });
      else if (catalog && !catalog.has(op.componentId)) {
        issues.push({ path: 'componentId', message: `unknown component "${op.componentId}"`, severity: 'error' });
      }
      if (op.target) {
        if (!sectionExists(layout, op.target.sectionId)) {
          issues.push({ path: 'target.sectionId', message: `unknown section "${op.target.sectionId}"`, severity: 'error' });
        } else if (op.target.columnId && !columnExists(layout, op.target.sectionId, op.target.columnId)) {
          issues.push({ path: 'target.columnId', message: `unknown column "${op.target.columnId}"`, severity: 'error' });
        }
      }
      if (catalog && op.config) {
        const result = catalog.validateConfig(op.componentId, op.config);
        issues.push(...result.issues.map(i => ({ ...i, path: `config.${i.path}` })));
      }
      break;
    }
    case 'remove_widget':
    case 'move_widget':
    case 'reorder_widget':
    case 'resize_widget':
    case 'update_config':
    case 'duplicate_widget': {
      if (!locate(layout, op.instanceId)) {
        issues.push({ path: 'instanceId', message: `unknown widget instance "${op.instanceId}"`, severity: 'error' });
      }
      if (op.op === 'move_widget' && !sectionExists(layout, op.target.sectionId)) {
        issues.push({ path: 'target.sectionId', message: `unknown section "${op.target.sectionId}"`, severity: 'error' });
      }
      if (op.op === 'update_config') {
        const found = locate(layout, op.instanceId);
        if (found && catalog) {
          const merged = { ...(found.widget.config ?? {}), ...op.patch };
          const result = catalog.validateConfig(found.widget.widgetId, merged);
          issues.push(...result.issues.map(i => ({ ...i, path: `patch.${i.path}` })));
        }
      }
      break;
    }
    case 'set_column_count': {
      if (!sectionExists(layout, op.sectionId)) {
        issues.push({ path: 'sectionId', message: `unknown section "${op.sectionId}"`, severity: 'error' });
      }
      if (!(Number.isInteger(op.count) && op.count >= 1 && op.count <= 4)) {
        issues.push({ path: 'count', message: 'column count must be an integer 1..4', severity: 'error' });
      }
      break;
    }
    case 'set_column_weight': {
      const owner = layout.sections.find(s => s.columns.some(c => c.id === op.columnId));
      if (!owner) issues.push({ path: 'columnId', message: `unknown column "${op.columnId}"`, severity: 'error' });
      if (!(Number.isFinite(op.weight) && op.weight > 0)) {
        issues.push({ path: 'weight', message: 'column weight must be a positive number', severity: 'error' });
      }
      break;
    }
    case 'remove_section': {
      if (!sectionExists(layout, op.sectionId)) {
        issues.push({ path: 'sectionId', message: `unknown section "${op.sectionId}"`, severity: 'error' });
      }
      break;
    }
    case 'update_meta': {
      if (op.title !== undefined && op.title.trim().length === 0) {
        issues.push({ path: 'title', message: 'title may not be empty', severity: 'error' });
      }
      break;
    }
  }
  return issues;
}

function insertPlacement(d: Draft<WorkspaceLayout>, placement: WidgetPlacement, target?: DropTarget, zone?: WorkspaceZone): void {
  let section = target ? d.sections.find(s => s.id === target.sectionId) : undefined;
  if (!section) {
    if (d.sections.length === 0) {
      d.sections.push({ id: newId('sec'), zone: zone ?? 'main', columns: [{ id: newId('col'), weight: 3, widgets: [] }] });
    }
    section = zone ? d.sections.find(s => (s.zone ?? 'main') === zone) : undefined;
    if (!section) section = d.sections[d.sections.length - 1];
  }
  let column = target?.columnId ? section.columns.find(c => c.id === target.columnId) : undefined;
  if (!column) {
    if (section.columns.length === 0) section.columns.push({ id: newId('col'), weight: 3, widgets: [] });
    column = section.columns[section.columns.length - 1];
  }
  const index = target && column.id === target.columnId
    ? Math.max(0, Math.min(target.index, column.widgets.length))
    : column.widgets.length;
  column.widgets.splice(index, 0, placement);
}

function applyOne(d: Draft<WorkspaceLayout>, op: BlueprintOp, blueprint: UiBlueprint): void {
  switch (op.op) {
    case 'add_widget': {
      const placement: WidgetPlacement = {
        id: op.instanceId ?? newId('wid'),
        widgetId: op.componentId,
        height: op.height ?? null,
        ...(op.config ? { config: { ...op.config } } : {}),
      };
      insertPlacement(d, placement, op.target, op.zone);
      break;
    }
    case 'remove_widget':
      removeWidget(d, op.instanceId);
      break;
    case 'move_widget':
      moveWidget(d, op.instanceId, op.target);
      break;
    case 'reorder_widget': {
      const found = locate(d as WorkspaceLayout, op.instanceId);
      if (found) {
        const column = found.column;
        const from = column.widgets.findIndex(w => w.id === op.instanceId);
        const to = Math.max(0, Math.min(op.toIndex, column.widgets.length - 1));
        if (from !== -1 && from !== to) {
          const [item] = column.widgets.splice(from, 1);
          column.widgets.splice(to, 0, item);
        }
      }
      break;
    }
    case 'resize_widget':
      setWidgetHeight(d, op.instanceId, op.height);
      break;
    case 'update_config':
      setWidgetConfig(d, op.instanceId, op.patch);
      break;
    case 'duplicate_widget':
      duplicateWidget(d, op.instanceId);
      break;
    case 'set_column_count':
      setColumnCount(d, op.sectionId, op.count);
      break;
    case 'set_column_weight':
      setColumnWeight(d, op.columnId, op.weight);
      break;
    case 'remove_section':
      removeSection(d, op.sectionId);
      break;
    case 'update_meta':
      break;
  }
  void blueprint;
}

/**
 * Validate and atomically apply a batch of operations. All-or-nothing: if any op
 * fails validation the blueprint is returned unchanged with the issues.
 */
export function applyBlueprintOps(
  blueprint: UiBlueprint,
  ops: BlueprintOp[],
  opts: ApplyBlueprintOpsOptions = {},
): ApplyBlueprintOpsResult {
  const issues = ops.flatMap(op => validateOp(op, blueprint, opts.catalog));
  if (issues.some(i => i.severity === 'error')) {
    return { ok: false, blueprint, issues, applied: 0 };
  }
  if (ops.length === 0) {
    return { ok: true, blueprint, issues: [], applied: 0 };
  }

  const nextLayout = produce(blueprint.layout, draft => {
    for (const op of ops) applyOne(draft, op, blueprint);
  });

  const metaOps = ops.filter((op): op is Extract<BlueprintOp, { op: 'update_meta' }> => op.op === 'update_meta');
  const meta = metaOps.reduce((acc, op) => ({ ...acc, ...op }), {} as Record<string, unknown>);

  const updated: UiBlueprint = {
    ...blueprint,
    layout: nextLayout,
    ...(meta.title !== undefined ? { title: meta.title as string } : {}),
    ...(meta.description !== undefined ? { description: meta.description as string } : {}),
    ...(meta.path !== undefined ? { path: meta.path as string } : {}),
    ...(meta.tags !== undefined ? { tags: meta.tags as string[] } : {}),
  };

  return { ok: true, blueprint: touchBlueprint(updated, opts.now), issues: [], applied: ops.length };
}

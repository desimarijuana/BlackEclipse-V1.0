// ── Blueprint revision history, diff and conflict detection ──────────────────
// The audit + recovery layer for blueprints. It answers three questions the
// agent and the builder both need: "what changed?", "give me the previous
// valid state", and "am I about to overwrite someone else's edit?". Snapshots
// are full blueprints so restore is exact; history is bounded so memory stays
// flat on a long editing session.

import type { UiBlueprint } from './blueprint';
import { touchBlueprint } from './blueprint';
import { locate } from '@/lib/workspace/ops';
import type { WorkspaceLayout, WidgetPlacement } from '@/lib/workspace/types';

export type BlueprintChangeType =
  | 'add_widget'
  | 'remove_widget'
  | 'move_widget'
  | 'resize_widget'
  | 'config_changed'
  | 'meta_changed'
  | 'layout_changed';

export interface BlueprintChange {
  type: BlueprintChangeType;
  instanceId?: string;
  componentId?: string;
  detail: string;
}

interface IndexedPlacement {
  placement: WidgetPlacement;
  sectionIndex: number;
  columnIndex: number;
  widgetIndex: number;
}

function indexPlacements(layout: WorkspaceLayout): Map<string, IndexedPlacement> {
  const map = new Map<string, IndexedPlacement>();
  layout.sections.forEach((section, sectionIndex) => {
    section.columns.forEach((column, columnIndex) => {
      column.widgets.forEach((placement, widgetIndex) => {
        map.set(placement.id, { placement, sectionIndex, columnIndex, widgetIndex });
      });
    });
  });
  return map;
}

function configSignature(placement: WidgetPlacement): string {
  return JSON.stringify(placement.config ?? {});
}

/** Structural, human-readable difference between two blueprints' layouts/meta. */
export function diffBlueprints(from: UiBlueprint, to: UiBlueprint): BlueprintChange[] {
  const changes: BlueprintChange[] = [];
  const before = indexPlacements(from.layout);
  const after = indexPlacements(to.layout);

  for (const [id, entry] of after) {
    if (!before.has(id)) {
      changes.push({ type: 'add_widget', instanceId: id, componentId: entry.placement.widgetId, detail: `added ${entry.placement.widgetId}` });
    }
  }
  for (const [id, entry] of before) {
    if (!after.has(id)) {
      changes.push({ type: 'remove_widget', instanceId: id, componentId: entry.placement.widgetId, detail: `removed ${entry.placement.widgetId}` });
    }
  }
  for (const [id, next] of after) {
    const prev = before.get(id);
    if (!prev) continue;
    if (
      prev.sectionIndex !== next.sectionIndex ||
      prev.columnIndex !== next.columnIndex ||
      prev.widgetIndex !== next.widgetIndex
    ) {
      changes.push({ type: 'move_widget', instanceId: id, componentId: next.placement.widgetId, detail: `moved ${next.placement.widgetId}` });
    }
    if (prev.placement.height !== next.placement.height) {
      changes.push({ type: 'resize_widget', instanceId: id, componentId: next.placement.widgetId, detail: `resized ${next.placement.widgetId}` });
    }
    if (configSignature(prev.placement) !== configSignature(next.placement)) {
      changes.push({ type: 'config_changed', instanceId: id, componentId: next.placement.widgetId, detail: `reconfigured ${next.placement.widgetId}` });
    }
  }

  const metaChanged = from.title !== to.title || from.description !== to.description || from.path !== to.path || JSON.stringify(from.tags ?? []) !== JSON.stringify(to.tags ?? []);
  if (metaChanged) changes.push({ type: 'meta_changed', detail: 'updated page metadata' });

  const sectionShapeBefore = from.layout.sections.map(s => `${s.id}:${s.columns.length}:${s.columns.map(c => c.weight).join(',')}`).join('|');
  const sectionShapeAfter = to.layout.sections.map(s => `${s.id}:${s.columns.length}:${s.columns.map(c => c.weight).join(',')}`).join('|');
  if (sectionShapeBefore !== sectionShapeAfter) changes.push({ type: 'layout_changed', detail: 'changed section/column layout' });

  return changes;
}

export interface RevisionEntry {
  revision: number;
  timestamp: string;
  summary: string;
  changes: BlueprintChange[];
  blueprint: UiBlueprint;
}

/** Bounded history of blueprint snapshots with exact restore + undo. */
export class BlueprintHistory {
  private entries: RevisionEntry[] = [];
  private readonly max: number;

  constructor(max = 50) {
    this.max = Math.max(2, max);
  }

  get length(): number {
    return this.entries.length;
  }

  /** Record a new blueprint state, deriving the change list from the previous. */
  record(blueprint: UiBlueprint, summary: string): RevisionEntry {
    const previous = this.entries[this.entries.length - 1];
    const entry: RevisionEntry = {
      revision: blueprint.revision,
      timestamp: blueprint.updatedAt,
      summary,
      changes: previous ? diffBlueprints(previous.blueprint, blueprint) : [],
      blueprint,
    };
    this.entries.push(entry);
    if (this.entries.length > this.max) this.entries.splice(0, this.entries.length - this.max);
    return entry;
  }

  list(): RevisionEntry[] {
    return [...this.entries];
  }

  get(revision: number): RevisionEntry | undefined {
    return this.entries.find(e => e.revision === revision);
  }

  latest(): RevisionEntry | undefined {
    return this.entries[this.entries.length - 1];
  }

  /** The blueprint as of the revision before `revision`, if retained. */
  previousOf(revision: number): UiBlueprint | undefined {
    const idx = this.entries.findIndex(e => e.revision === revision);
    if (idx <= 0) return undefined;
    return this.entries[idx - 1].blueprint;
  }

  /** Undo: the previous retained state of the latest revision. */
  undoSnapshot(): UiBlueprint | undefined {
    const latest = this.latest();
    if (!latest) return undefined;
    return this.previousOf(latest.revision);
  }
}

export interface RevertResult {
  ok: boolean;
  blueprint?: UiBlueprint;
  fromRevision?: number;
  toRevision?: number;
  reason?: string;
}

/**
 * Restore a blueprint to an earlier snapshot as a NEW revision (history is
 * append-only; a restore is never itself a destructive rewrite). The restored
 * blueprint's identity/metadata are kept but its revision is bumped.
 */
export function restoreRevision(history: BlueprintHistory, revision: number, now?: string): RevertResult {
  const entry = history.get(revision);
  if (!entry) return { ok: false, reason: `revision ${revision} is not retained` };
  // Restore is appended as a NEW revision above the latest, so it can never
  // collide with an existing revision number in the history.
  const latestRevision = history.latest()?.revision ?? entry.blueprint.revision;
  const restored: UiBlueprint = {
    ...touchBlueprint(entry.blueprint, now),
    revision: latestRevision + 1,
  };
  return { ok: true, blueprint: restored, fromRevision: entry.blueprint.revision, toRevision: restored.revision };
}

export interface RevisionConflict {
  conflict: true;
  expected: number;
  actual: number;
  message: string;
}

/** Optimistic-concurrency check: has the stored revision moved past the writer's base? */
export function detectConflict(expectedRevision: number, current: UiBlueprint): RevisionConflict | null {
  if (expectedRevision === current.revision) return null;
  return {
    conflict: true,
    expected: expectedRevision,
    actual: current.revision,
    message: `blueprint moved from revision ${expectedRevision} to ${current.revision}; reload and re-apply`,
  };
}

/** Locate helper re-exported for callers that target a component instance. */
export { locate };

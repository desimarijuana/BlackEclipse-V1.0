import { describe, expect, it } from 'vitest';
import type { WorkspaceLayout } from '@/lib/workspace/types';
import { createBlueprint } from './blueprint';
import {
  BlueprintHistory,
  detectConflict,
  diffBlueprints,
  restoreRevision,
} from './revisions';

function layout(widgets: Array<{ id: string; widgetId: string; config?: Record<string, unknown> }> = [], height: Record<string, number> = {}): WorkspaceLayout {
  return {
    version: 2,
    sections: [{
      id: 's1',
      zone: 'main',
      columns: [{
        id: 'c1',
        weight: 3,
        widgets: widgets.map(w => ({ id: w.id, widgetId: w.widgetId, height: height[w.id] ?? null, config: w.config })),
      }],
    }],
  };
}

describe('diffBlueprints', () => {
  it('detects add, remove, move, resize, config and meta changes', () => {
    const before = createBlueprint({ title: 'Home', layout: layout([{ id: 'w1', widgetId: 'a' }]), now: '2026-01-01T00:00:00.000Z' });
    const after = createBlueprint({
      title: 'Home 2',
      layout: {
        version: 2,
        sections: [{
          id: 's1',
          zone: 'main',
          columns: [
            { id: 'c1', weight: 3, widgets: [] },
            { id: 'c2', weight: 3, widgets: [{ id: 'w1', widgetId: 'a', height: 300, config: { x: 1 } }, { id: 'w2', widgetId: 'b', height: null }] },
          ],
        }],
      },
    });
    const changes = diffBlueprints(before, after);
    const types = changes.map(c => c.type);
    expect(types).toContain('add_widget');
    expect(types).toContain('move_widget');
    expect(types).toContain('resize_widget');
    expect(types).toContain('config_changed');
    expect(types).toContain('layout_changed');
    expect(types).toContain('meta_changed');
  });

  it('reports removed widgets', () => {
    const before = createBlueprint({ title: 'H', layout: layout([{ id: 'w1', widgetId: 'a' }, { id: 'w2', widgetId: 'b' }]) });
    const after = createBlueprint({ title: 'H', layout: layout([{ id: 'w1', widgetId: 'a' }]) });
    expect(diffBlueprints(before, after).some(c => c.type === 'remove_widget' && c.instanceId === 'w2')).toBe(true);
  });
});

describe('BlueprintHistory', () => {
  it('records snapshots deriving change lists', () => {
    const history = new BlueprintHistory();
    const v1 = createBlueprint({ title: 'H', layout: layout([{ id: 'w1', widgetId: 'a' }]) });
    const v2 = createBlueprint({ title: 'H', layout: layout([{ id: 'w1', widgetId: 'a' }, { id: 'w2', widgetId: 'b' }]) });
    v2.revision = 2;
    history.record(v1, 'created');
    history.record(v2, 'added w2');
    expect(history.list()).toHaveLength(2);
    expect(history.latest()?.summary).toBe('added w2');
    expect(history.latest()?.changes.some(c => c.type === 'add_widget')).toBe(true);
    expect(history.previousOf(2)?.id).toBe(v1.id);
    expect(history.undoSnapshot()?.revision).toBe(1);
  });

  it('stays bounded', () => {
    const history = new BlueprintHistory(3);
    for (let i = 1; i <= 6; i++) {
      const bp = createBlueprint({ title: 'H', layout: layout() });
      bp.revision = i;
      history.record(bp, `r${i}`);
    }
    expect(history.length).toBe(3);
  });

  it('restores an earlier revision as a new revision', () => {
    const history = new BlueprintHistory();
    const v1 = createBlueprint({ title: 'H', layout: layout([{ id: 'w1', widgetId: 'a' }]) });
    v1.revision = 1;
    const v2 = createBlueprint({ title: 'H', layout: layout([{ id: 'w1', widgetId: 'a' }, { id: 'w2', widgetId: 'b' }]) });
    v2.revision = 2;
    history.record(v1, 'created');
    history.record(v2, 'added');
    const restored = restoreRevision(history, 1, '2026-03-01T00:00:00.000Z');
    expect(restored.ok).toBe(true);
    expect(restored.blueprint?.revision).toBe(3);
    expect(restored.blueprint?.layout.sections[0].columns[0].widgets).toHaveLength(1);
    expect(restoreRevision(history, 99).ok).toBe(false);
  });
});

describe('detectConflict', () => {
  it('returns null when revisions match and a conflict when they differ', () => {
    const bp = createBlueprint({ title: 'H', layout: layout() });
    expect(detectConflict(1, bp)).toBeNull();
    const conflict = detectConflict(1, { ...bp, revision: 3 });
    expect(conflict?.conflict).toBe(true);
    expect(conflict?.expected).toBe(1);
    expect(conflict?.actual).toBe(3);
  });
});

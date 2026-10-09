import { describe, expect, it } from 'vitest';
import type { WidgetDefinition } from '@/lib/workspace/widget-def';
import type { WorkspaceLayout } from '@/lib/workspace/types';
import { locate } from '@/lib/workspace/ops';
import { ComponentCatalog, adaptWidgetDefinition } from './catalog';
import { createBlueprint, type UiBlueprint } from './blueprint';
import { applyBlueprintOps } from './patches';

function def(id: string): WidgetDefinition {
  return { id, category: 'markets', label: id, desc: id, icon: 'activity', sizes: ['medium'] };
}
const catalog = new ComponentCatalog([adaptWidgetDefinition(def('a')), adaptWidgetDefinition(def('b'))]);

function layout(): WorkspaceLayout {
  return {
    version: 2,
    sections: [{
      id: 's1',
      zone: 'main',
      columns: [
        { id: 'c1', weight: 3, widgets: [{ id: 'w1', widgetId: 'a', height: null }] },
        { id: 'c2', weight: 3, widgets: [] },
      ],
    }],
  };
}

function bp(): UiBlueprint {
  return createBlueprint({ title: 'Home', layout: layout(), now: '2026-01-01T00:00:00.000Z' });
}

describe('applyBlueprintOps', () => {
  it('adds a widget with a controlled instance id and bumps the revision', () => {
    const result = applyBlueprintOps(bp(), [{ op: 'add_widget', componentId: 'b', instanceId: 'x1', target: { sectionId: 's1', columnId: 'c2', index: 0 } }], { catalog, now: '2026-01-02T00:00:00.000Z' });
    expect(result.ok).toBe(true);
    expect(result.applied).toBe(1);
    expect(result.blueprint.revision).toBe(2);
    expect(locate(result.blueprint.layout, 'x1')?.widget.widgetId).toBe('b');
  });

  it('rejects an unknown component and leaves the blueprint unchanged', () => {
    const start = bp();
    const result = applyBlueprintOps(start, [{ op: 'add_widget', componentId: 'ghost' }], { catalog });
    expect(result.ok).toBe(false);
    expect(result.blueprint).toBe(start);
    expect(result.blueprint.revision).toBe(1);
  });

  it('removes, moves, resizes, reconfigures and duplicates widgets', () => {
    const add = applyBlueprintOps(bp(), [{ op: 'add_widget', componentId: 'b', instanceId: 'x1', target: { sectionId: 's1', columnId: 'c1', index: 0 } }], { catalog });
    const batch = applyBlueprintOps(add.blueprint, [
      { op: 'move_widget', instanceId: 'x1', target: { sectionId: 's1', columnId: 'c2', index: 0 } },
      { op: 'resize_widget', instanceId: 'w1', height: 320 },
      { op: 'update_config', instanceId: 'w1', patch: { symbol: 'AAPL' } },
      { op: 'duplicate_widget', instanceId: 'w1' },
    ], { catalog });
    expect(batch.ok).toBe(true);
    expect(locate(batch.blueprint.layout, 'x1')?.column.id).toBe('c2');
    expect(locate(batch.blueprint.layout, 'w1')?.widget.height).toBe(320);
    expect(locate(batch.blueprint.layout, 'w1')?.widget.config).toEqual({ symbol: 'AAPL' });
    const col1 = batch.blueprint.layout.sections[0].columns[0];
    expect(col1.widgets).toHaveLength(2);

    const removed = applyBlueprintOps(batch.blueprint, [{ op: 'remove_widget', instanceId: 'x1' }], { catalog });
    expect(removed.ok).toBe(true);
    expect(locate(removed.blueprint.layout, 'x1')).toBeNull();
  });

  it('updates page metadata', () => {
    const result = applyBlueprintOps(bp(), [{ op: 'update_meta', title: 'Renamed', description: 'desc', tags: ['x'] }], { catalog });
    expect(result.ok).toBe(true);
    expect(result.blueprint.title).toBe('Renamed');
    expect(result.blueprint.description).toBe('desc');
    expect(result.blueprint.tags).toEqual(['x']);
  });

  it('is atomic: one bad op in a batch changes nothing', () => {
    const start = bp();
    const result = applyBlueprintOps(start, [
      { op: 'add_widget', componentId: 'b', instanceId: 'x1' },
      { op: 'remove_widget', instanceId: 'missing' },
    ], { catalog });
    expect(result.ok).toBe(false);
    expect(result.blueprint).toBe(start);
    expect(locate(start.layout, 'x1')).toBeNull();
  });

  it('manages columns and sections', () => {
    const grow = applyBlueprintOps(bp(), [{ op: 'set_column_count', sectionId: 's1', count: 3 }], { catalog });
    expect(grow.blueprint.layout.sections[0].columns).toHaveLength(3);
    const weight = applyBlueprintOps(grow.blueprint, [{ op: 'set_column_weight', columnId: 'c1', weight: 5 }], { catalog });
    expect(weight.blueprint.layout.sections[0].columns[0].weight).toBe(5);
    const removed = applyBlueprintOps(weight.blueprint, [{ op: 'remove_section', sectionId: 's1' }], { catalog });
    expect(removed.blueprint.layout.sections).toHaveLength(1);
  });

  it('reorders within a column', () => {
    const withTwo = applyBlueprintOps(bp(), [{ op: 'add_widget', componentId: 'b', instanceId: 'x1', target: { sectionId: 's1', columnId: 'c1', index: 1 } }], { catalog });
    const reordered = applyBlueprintOps(withTwo.blueprint, [{ op: 'reorder_widget', instanceId: 'x1', toIndex: 0 }], { catalog });
    expect(reordered.blueprint.layout.sections[0].columns[0].widgets.map(w => w.id)).toEqual(['x1', 'w1']);
  });
});

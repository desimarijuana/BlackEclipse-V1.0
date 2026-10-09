import { describe, expect, it } from 'vitest';
import type { WorkspaceLayout } from '@/lib/workspace/types';
import { ComponentCatalog, adaptWidgetDefinition } from './catalog';
import { createBlueprint, touchBlueprint, validateBlueprint, validateLayout } from './blueprint';
import type { WidgetDefinition } from '@/lib/workspace/widget-def';

function def(id: string): WidgetDefinition {
  return { id, category: 'markets', label: id, desc: id, icon: 'activity', sizes: ['medium'] };
}
const catalog = new ComponentCatalog([adaptWidgetDefinition(def('a')), adaptWidgetDefinition(def('b'))]);

function layout(widgetIds: string[] = ['a']): WorkspaceLayout {
  return {
    version: 2,
    sections: [{
      id: 's1',
      zone: 'main',
      columns: [{ id: 'c1', weight: 3, widgets: widgetIds.map((widgetId, i) => ({ id: `w${i}`, widgetId, height: null })) }],
    }],
  };
}

describe('createBlueprint / touchBlueprint', () => {
  it('creates a blueprint at revision 1 with defaults', () => {
    const bp = createBlueprint({ title: 'Home', layout: layout(), now: '2026-01-01T00:00:00.000Z' });
    expect(bp.revision).toBe(1);
    expect(bp.kind).toBe('page');
    expect(bp.scope).toBe('personal');
    expect(bp.owner).toEqual({ kind: 'user', id: 'operator' });
    expect(bp.createdAt).toBe('2026-01-01T00:00:00.000Z');
    expect(bp.id).toMatch(/^bp-/);
  });

  it('bumps revision and timestamp on touch', () => {
    const bp = createBlueprint({ title: 'Home', layout: layout() });
    const next = touchBlueprint(bp, '2026-02-01T00:00:00.000Z');
    expect(next.revision).toBe(2);
    expect(next.updatedAt).toBe('2026-02-01T00:00:00.000Z');
  });
});

describe('validateBlueprint', () => {
  it('accepts a valid blueprint and returns the cleaned shape', () => {
    const bp = createBlueprint({ title: 'Home', layout: layout(['a', 'b']), kind: 'workspace', scope: 'shared' });
    const result = validateBlueprint(bp, catalog);
    expect(result.ok).toBe(true);
    expect(result.blueprint?.schemaVersion).toBe(1);
    expect(result.blueprint?.kind).toBe('workspace');
    expect(result.blueprint?.scope).toBe('shared');
  });

  it('rejects an unknown component', () => {
    const bp = createBlueprint({ title: 'Home', layout: layout(['ghost']) });
    const result = validateBlueprint(bp, catalog);
    expect(result.ok).toBe(false);
    expect(result.issues.some(i => i.message.includes('unknown component "ghost"'))).toBe(true);
  });

  it('rejects duplicate instance ids', () => {
    const bp = createBlueprint({ title: 'Home', layout: layout(['a', 'a']) });
    bp.layout.sections[0].columns[0].widgets[1].id = 'w0';
    const result = validateBlueprint(bp, catalog);
    expect(result.ok).toBe(false);
    expect(result.issues.some(i => i.message.includes('duplicate instance id'))).toBe(true);
  });

  it('rejects an invalid configuration', () => {
    const withField = new ComponentCatalog([
      adaptWidgetDefinition({ ...def('a'), configFields: [{ key: 'limit', label: 'Limit', type: 'number', min: 1, max: 10 }] }),
    ]);
    const bp = createBlueprint({ title: 'Home', layout: layout(['a']) });
    bp.layout.sections[0].columns[0].widgets[0].config = { limit: 999 };
    const result = validateBlueprint(bp, withField);
    expect(result.ok).toBe(false);
    expect(result.issues.some(i => i.path.includes('config.limit'))).toBe(true);
  });

  it('rejects a future schema version and a missing title', () => {
    const bp = createBlueprint({ title: 'Home', layout: layout() });
    const future = { ...bp, schemaVersion: 99 };
    expect(validateBlueprint(future, catalog).ok).toBe(false);
    const noTitle = { ...bp, title: '' };
    expect(validateBlueprint(noTitle, catalog).issues.some(i => i.path === 'title')).toBe(true);
  });

  it('reports structural layout problems', () => {
    const { issues, layout: clean } = validateLayout({ sections: [{ id: 's', columns: [] }] });
    expect(clean).toBeDefined();
    expect(issues.some(i => i.path.includes('columns') && i.message.includes('more than 4'))).toBe(false);
    expect(validateLayout({ sections: 'nope' }).issues[0].message).toContain('must be an array');
    expect(validateLayout(42).issues[0].message).toContain('must be an object');
  });
});

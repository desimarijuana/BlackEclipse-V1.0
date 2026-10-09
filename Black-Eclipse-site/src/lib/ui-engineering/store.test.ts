import { describe, expect, it } from 'vitest';
import type { StorageLike } from '@/lib/workspace/persistence';
import type { WorkspaceLayout } from '@/lib/workspace/types';
import { createBlueprint } from './blueprint';
import { createLocalBlueprintStore, createMemoryBlueprintStore } from './store';

function layout(widgets: string[] = []): WorkspaceLayout {
  return {
    version: 2,
    sections: [{ id: 's1', zone: 'main', columns: [{ id: 'c1', weight: 3, widgets: widgets.map((widgetId, i) => ({ id: `w${i}`, widgetId, height: null })) }] }],
  };
}

function memStorage(): StorageLike & { data: Map<string, string> } {
  const data = new Map<string, string>();
  return {
    data,
    getItem: k => (data.has(k) ? data.get(k)! : null),
    setItem: (k, v) => { data.set(k, v); },
    removeItem: k => { data.delete(k); },
  };
}

describe('createMemoryBlueprintStore', () => {
  it('saves, gets, lists and records history', () => {
    const store = createMemoryBlueprintStore();
    const bp = createBlueprint({ title: 'Home', layout: layout(['a']) });
    const saved = store.save(bp);
    expect(saved.ok).toBe(true);
    expect(store.get(bp.id)?.title).toBe('Home');
    expect(store.list()).toHaveLength(1);
    expect(store.list()[0]).toMatchObject({ id: bp.id, revision: 1, widgetCount: 1, ownerId: 'operator' });
    expect(store.history(bp.id)).toHaveLength(1);

    const bumped = { ...store.get(bp.id)!, revision: 2, title: 'Home 2' };
    expect(store.save(bumped).ok).toBe(true);
    expect(store.history(bp.id)).toHaveLength(2);
  });

  it('filters by scope, owner and kind', () => {
    const store = createMemoryBlueprintStore();
    store.save(createBlueprint({ title: 'A', layout: layout(), scope: 'personal' }));
    store.save(createBlueprint({ title: 'B', layout: layout(), scope: 'shared', kind: 'workspace', owner: { kind: 'plugin', id: 'hello' } }));
    expect(store.list({ scope: 'shared' })).toHaveLength(1);
    expect(store.list({ ownerId: 'hello' })).toHaveLength(1);
    expect(store.list({ kind: 'workspace' })).toHaveLength(1);
  });

  it('enforces optimistic concurrency', () => {
    const store = createMemoryBlueprintStore();
    const bp = store.save(createBlueprint({ title: 'Home', layout: layout() })).blueprint!;
    const moved = store.save({ ...bp, revision: 2, title: 'Current' }).blueprint!;
    expect(moved.revision).toBe(2);
    const stale = { ...bp, revision: 2, title: 'Stale' };
    const result = store.save(stale, { expectedRevision: 1 });
    expect(result.ok).toBe(false);
    expect(result.conflict?.actual).toBe(2);
    expect(store.get(bp.id)?.title).toBe('Current');
  });

  it('rejects an invalid blueprint', () => {
    const store = createMemoryBlueprintStore();
    const invalid = { ...createBlueprint({ title: 'Home', layout: layout() }), title: '' };
    const result = store.save(invalid);
    expect(result.ok).toBe(false);
    expect(result.issues?.some(i => i.path === 'title')).toBe(true);
  });

  it('removes blueprints', () => {
    const store = createMemoryBlueprintStore();
    const bp = store.save(createBlueprint({ title: 'Home', layout: layout() })).blueprint!;
    expect(store.remove(bp.id)).toBe(true);
    expect(store.remove(bp.id)).toBe(false);
    expect(store.get(bp.id)).toBeNull();
  });
});

describe('createLocalBlueprintStore', () => {
  it('persists across store instances and ignores corrupt payloads', () => {
    const storage = memStorage();
    const first = createLocalBlueprintStore({ storage });
    const bp = first.save(createBlueprint({ title: 'Home', layout: layout(['a']) })).blueprint!;

    const second = createLocalBlueprintStore({ storage });
    expect(second.get(bp.id)?.title).toBe('Home');
    expect(second.history(bp.id)).toHaveLength(1);

    storage.setItem('eclipse:ui-blueprints:v1', '{not json');
    const third = createLocalBlueprintStore({ storage });
    expect(third.list()).toEqual([]);
    expect(first.get(bp.id)?.id).toBe(bp.id);
  });
});

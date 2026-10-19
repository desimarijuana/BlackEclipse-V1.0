import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { WidgetDefinition } from './widget-def';
import {
  clearWidgetRegistry,
  getWidget,
  listWidgets,
  registerWidget,
  subscribeWidgets,
  unregisterWidget,
} from './widget-registry';

function widget(id: string, surface?: WidgetDefinition['surface']): WidgetDefinition {
  return {
    id,
    category: 'tools',
    label: id,
    desc: id,
    icon: 'dashboard',
    sizes: ['medium'],
    surface,
  };
}

beforeEach(() => clearWidgetRegistry());

describe('widget registry', () => {
  it('preserves registration order', () => {
    registerWidget(widget('a'));
    registerWidget(widget('b'));
    registerWidget(widget('c'));
    expect(listWidgets().map((w) => w.id)).toEqual(['a', 'b', 'c']);
  });

  it('ignores duplicates unless replace is requested', () => {
    registerWidget(widget('a'));
    registerWidget({ ...widget('a'), label: 'second' });
    expect(getWidget('a')?.label).toBe('a');
    registerWidget({ ...widget('a'), label: 'third' }, { replace: true });
    expect(getWidget('a')?.label).toBe('third');
  });

  it('filters by surface while keeping shared widgets', () => {
    registerWidget(widget('dashboard-only', 'dashboard'));
    registerWidget(widget('page-only', 'page'));
    registerWidget(widget('shared', 'both'));
    registerWidget(widget('implicit'));
    expect(listWidgets({ surface: 'dashboard' }).map((w) => w.id)).toEqual([
      'dashboard-only', 'shared', 'implicit',
    ]);
    expect(listWidgets({ surface: 'page' }).map((w) => w.id)).toEqual([
      'page-only', 'shared', 'implicit',
    ]);
  });

  it('notifies subscribers on register and unregister', () => {
    const listener = vi.fn();
    const unsubscribe = subscribeWidgets(listener);
    registerWidget(widget('a'));
    unregisterWidget('a');
    unsubscribe();
    registerWidget(widget('b'));
    expect(listener).toHaveBeenCalledTimes(2);
  });
});

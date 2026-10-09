import { describe, expect, it } from 'vitest';
import type { WidgetDefinition } from '@/lib/workspace/widget-def';
import {
  adaptWidgetDefinition,
  ComponentCatalog,
  validateComponentConfig,
  type UiComponentSpec,
} from './catalog';

function widget(over: Partial<WidgetDefinition> = {}): WidgetDefinition {
  return {
    id: 'metric-card',
    category: 'markets',
    label: 'Metric Card',
    desc: 'A headline metric',
    icon: 'activity',
    sizes: ['small', 'medium'],
    dataDeps: ['market:indices:US'],
    configFields: [
      { key: 'symbol', label: 'Symbol', type: 'symbol', placeholder: 'AAPL' },
      { key: 'limit', label: 'Limit', type: 'number', min: 1, max: 100, default: 20 },
      { key: 'mode', label: 'Mode', type: 'select', options: [{ value: 'a', label: 'A' }, { value: 'b', label: 'B' }] },
      { key: 'show', label: 'Show', type: 'boolean' },
      { key: 'symbols', label: 'Symbols', type: 'symbols' },
      { key: 'requiredThing', label: 'Required', type: 'text' },
    ],
    defaultConfig: { limit: 20 },
    ...over,
  };
}

describe('adaptWidgetDefinition', () => {
  it('maps registry metadata into a catalog spec', () => {
    const spec = adaptWidgetDefinition(widget());
    expect(spec.id).toBe('metric-card');
    expect(spec.displayName).toBe('Metric Card');
    expect(spec.category).toBe('markets');
    expect(spec.dataSources).toEqual(['market:indices:US']);
    expect(spec.defaultConfig).toEqual({ limit: 20 });
    expect(spec.configSchema.map(f => f.key)).toEqual(['symbol', 'limit', 'mode', 'show', 'symbols', 'requiredThing']);
    expect(spec.availability).toBe('available');
    expect(spec.owner).toBe('core');
  });

  it('honours ownership/availability overrides', () => {
    const spec = adaptWidgetDefinition(widget(), { owner: 'plugin', pluginId: 'hello-world', availability: 'unavailable' });
    expect(spec.owner).toBe('plugin');
    expect(spec.pluginId).toBe('hello-world');
    expect(spec.availability).toBe('unavailable');
  });
});

describe('ComponentCatalog', () => {
  const spec = (id: string, over: Partial<UiComponentSpec> = {}): UiComponentSpec => ({
    ...adaptWidgetDefinition(widget({ id, label: id, desc: `${id} description` })),
    ...over,
  });

  it('registers, gets and rejects duplicates', () => {
    const catalog = new ComponentCatalog([spec('a')]);
    expect(catalog.has('a')).toBe(true);
    expect(catalog.get('a')?.id).toBe('a');
    expect(() => catalog.register(spec('a'))).toThrow();
    catalog.register(spec('a'), { replace: true });
  });

  it('searches by text, category, data source and availability', () => {
    const catalog = new ComponentCatalog([
      spec('market-indices', { category: 'markets' }),
      spec('news-feed', { category: 'news', dataSources: ['news:feed'] }),
      spec('stub', { availability: 'unavailable', category: 'tools' }),
    ]);
    expect(catalog.search({ text: 'news' }).map(s => s.id)).toEqual(['news-feed']);
    expect(catalog.search({ category: 'markets' }).map(s => s.id)).toEqual(['market-indices']);
    expect(catalog.search({ dataSource: 'news:feed' }).map(s => s.id)).toEqual(['news-feed']);
    expect(catalog.search({ availability: 'unavailable' }).map(s => s.id)).toEqual(['stub']);
    expect(catalog.search({ text: 'nothing-matches' })).toEqual([]);
    expect(catalog.search({ limit: 1 })).toHaveLength(1);
  });

  it('lists categories and data sources', () => {
    const catalog = new ComponentCatalog([spec('a', { category: 'markets', dataSources: ['x'] }), spec('b', { category: 'news', dataSources: ['y'] })]);
    expect(catalog.categories()).toEqual(['markets', 'news']);
    expect(catalog.dataSources()).toEqual(['x', 'y']);
  });

  it('reports an unknown component on validateConfig', () => {
    const catalog = new ComponentCatalog();
    const result = catalog.validateConfig('missing', {});
    expect(result.ok).toBe(false);
    expect(result.issues[0].message).toContain('unknown component');
  });
});

describe('validateComponentConfig', () => {
  const base = adaptWidgetDefinition(widget());

  it('accepts a valid config', () => {
    const result = validateComponentConfig(base, { symbol: 'AAPL', limit: 10, mode: 'a', show: true, symbols: ['AAPL', 'MSFT'] });
    expect(result.ok).toBe(true);
    expect(result.issues).toEqual([]);
  });

  it('rejects wrong types', () => {
    const result = validateComponentConfig(base, { limit: 'ten', show: 'yes', symbols: 'AAPL' });
    expect(result.ok).toBe(false);
    expect(result.issues.filter(i => i.severity === 'error')).toHaveLength(3);
  });

  it('rejects out-of-range numbers and invalid select options', () => {
    const result = validateComponentConfig(base, { limit: 999, mode: 'z' });
    expect(result.ok).toBe(false);
    expect(result.issues.map(i => i.path)).toEqual(expect.arrayContaining(['limit', 'mode']));
  });

  it('warns on unknown keys without failing', () => {
    const result = validateComponentConfig(base, { somethingElse: 1 });
    expect(result.ok).toBe(true);
    expect(result.issues[0]).toMatchObject({ path: 'somethingElse', severity: 'warning' });
  });

  it('flags missing required fields', () => {
    const required = adaptWidgetDefinition(widget({ configFields: [{ key: 'need', label: 'Need', type: 'text' }] }));
    const schema = { ...required, configSchema: required.configSchema.map(f => ({ ...f, required: true })) };
    const result = validateComponentConfig(schema, {});
    expect(result.ok).toBe(false);
    expect(result.issues[0].message).toContain('missing required');
  });
});

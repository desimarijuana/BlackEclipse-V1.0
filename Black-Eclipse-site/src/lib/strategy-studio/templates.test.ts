import { describe, expect, it } from 'vitest';
import { STRATEGY_TEMPLATES, getTemplate } from './templates';

describe('strategy templates', () => {
  it('ships a handful of distinct templates', () => {
    expect(STRATEGY_TEMPLATES.length).toBeGreaterThanOrEqual(6);
    expect(new Set(STRATEGY_TEMPLATES.map((template) => template.id)).size).toBe(STRATEGY_TEMPLATES.length);
    expect(new Set(STRATEGY_TEMPLATES.map((template) => template.name)).size).toBe(STRATEGY_TEMPLATES.length);
  });

  it.each(STRATEGY_TEMPLATES.map((template) => [template.id, template] as const))(
    '%s is a complete, non-empty spec',
    (_id, template) => {
      const spec = template.spec as Record<string, unknown>;
      const strategy = spec.strategy as Record<string, unknown>;
      const universe = spec.universe as { symbols?: string[] };
      const rules = spec.rules as { entry?: { long?: unknown }; exit?: { stop_loss?: unknown } };

      expect(strategy.id).toBe(template.id);
      expect(String(strategy.name ?? '').length).toBeGreaterThan(0);
      expect(strategy.version).toBe('1.0.0');
      expect(universe.symbols?.length).toBeGreaterThan(0);
      expect(Array.isArray(spec.indicators)).toBe(true);
      expect((spec.indicators as unknown[]).length).toBeGreaterThan(0);
      expect(rules.entry?.long).toBeTruthy();
      expect(rules.exit?.stop_loss).toBeTruthy();
      expect(spec.position_sizing).toBeTruthy();
      expect(spec.execution).toBeTruthy();
    },
  );

  it('uses unique indicator ids inside each template', () => {
    for (const template of STRATEGY_TEMPLATES) {
      const indicators = (template.spec.indicators ?? []) as Array<{ id: string }>;
      const ids = indicators.map((indicator) => indicator.id);
      expect(new Set(ids).size).toBe(ids.length);
    }
  });

  it('round-trips through JSON (the editor is JSON text)', () => {
    for (const template of STRATEGY_TEMPLATES) {
      expect(JSON.parse(JSON.stringify(template.spec))).toEqual(template.spec);
    }
  });

  it('looks a template up by id', () => {
    expect(getTemplate('ema_trend')?.name).toBe('EMA trend');
    expect(getTemplate('missing')).toBeUndefined();
  });
});

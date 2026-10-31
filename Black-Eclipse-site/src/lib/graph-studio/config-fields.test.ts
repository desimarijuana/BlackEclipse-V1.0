import { describe, expect, it } from 'vitest';
import { fieldsFor, inlineFieldsFor } from './config-fields';
import { getNodeDefinition, listNodeDefinitions } from './registry';

describe('config field presentation', () => {
  it('returns exactly one field per config key for every registered node', () => {
    for (const def of listNodeDefinitions()) {
      const keys = Object.keys(def.defaultConfig()).sort();
      const fields = fieldsFor(def);
      expect(fields.map((field) => field.key).sort(), def.type).toEqual(keys);
    }
  });

  it('maps an inline field to a real input port for the From wire state', () => {
    for (const def of listNodeDefinitions()) {
      const inputIds = new Set(def.inputs.map((port) => port.id));
      for (const field of inlineFieldsFor(def)) {
        const port = field.port ?? field.key;
        // A field only claims a wire when the mapped port actually exists.
        if (field.port) expect(inputIds.has(port), `${def.type}.${field.key}`).toBe(true);
      }
    }
    const agent = getNodeDefinition('agent.research')!;
    expect(inlineFieldsFor(agent).find((field) => field.key === 'objective')?.port).toBe('query');
  });

  it('marks at most two scalar fields inline (never JSON)', () => {
    for (const def of listNodeDefinitions()) {
      const inline = inlineFieldsFor(def);
      expect(inline.length, def.type).toBeLessThanOrEqual(2);
      expect(inline.every((field) => field.kind !== 'json')).toBe(true);
      expect(inline.every((field) => field.inline === true || field.quick !== undefined)).toBe(true);
    }
  });

  it('keeps a stable cached reference per definition', () => {
    const def = getNodeDefinition('finance.history')!;
    expect(fieldsFor(def)).toBe(fieldsFor(def));
    expect(inlineFieldsFor(def)).toBe(inlineFieldsFor(def));
  });

  it('uses the declared labels and select options for high-traffic nodes', () => {
    const def = getNodeDefinition('finance.history')!;
    const fields = fieldsFor(def);
    const interval = fields.find((field) => field.key === 'interval');
    expect(interval?.kind).toBe('select');
    expect(interval?.options?.map((option) => option.value)).toContain('1d');
    expect(fields.find((field) => field.key === 'symbol')?.label).toBe('Symbol');

    const sort = getNodeDefinition('transform.sort_limit')!;
    const order = fieldsFor(sort).find((field) => field.key === 'order');
    expect(order?.options?.map((option) => option.value)).toEqual(['asc', 'desc']);
    expect(inlineFieldsFor(sort).map((field) => field.key)).toEqual(['field', 'order']);
  });

  it('keeps the manual trigger zero-config', () => {
    const def = getNodeDefinition('trigger.manual')!;
    expect(def.defaultConfig()).toEqual({});
    expect(fieldsFor(def)).toEqual([]);
    expect(inlineFieldsFor(def)).toEqual([]);
  });

  it('promotes quick-priority fields into the two inline slots', () => {
    const condition = getNodeDefinition('logic.condition')!;
    expect(inlineFieldsFor(condition).map((field) => field.key)).toEqual(['operator', 'compareTo']);

    const research = getNodeDefinition('agent.research')!;
    expect(inlineFieldsFor(research).map((field) => field.key)).toEqual(['objective', 'agent']);
  });

  it('falls back to a humanized text/number/boolean/json field when unannotated', () => {
    const def = getNodeDefinition('logic.merge')!;
    expect(fieldsFor(def)).toMatchObject([
      { key: 'strategy', label: 'Strategy', kind: 'text' },
    ]);
    const quant = getNodeDefinition('quant.zscore')!;
    expect(fieldsFor(quant)).toMatchObject([
      { key: 'period', label: 'Period', kind: 'number', inline: true, min: 2, max: 500 },
    ]);
  });
});

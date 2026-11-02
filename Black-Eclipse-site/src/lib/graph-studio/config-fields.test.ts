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

  it('never shows a newer version’s fields on a saved older node', () => {
    const v1 = getNodeDefinition('integration.http', '1.0.0')!;
    const v11 = getNodeDefinition('integration.http', '1.1.0')!;
    const oldKeys = fieldsFor(v1).map((field) => field.key);
    const newKeys = fieldsFor(v11).map((field) => field.key);
    expect(oldKeys).not.toContain('retries');
    expect(newKeys).toContain('retries');
    expect(fieldsFor(v11).find((field) => field.key === 'bodyMode')?.kind).toBe('select');
    expect(fieldsFor(v11).find((field) => field.key === 'bodyMode')?.options?.map((option) => option.value))
      .toEqual(['json', 'text', 'form']);
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

  it('presents the transform-node controls', () => {
    const join = getNodeDefinition('transform.join')!;
    const joinFields = fieldsFor(join);
    expect(joinFields.find((field) => field.key === 'how')?.options?.map((option) => option.value))
      .toEqual(['inner', 'left', 'right', 'full', 'anti']);
    expect(joinFields.find((field) => field.key === 'onDuplicate')?.kind).toBe('select');
    expect(joinFields.find((field) => field.key === 'caseInsensitive')?.kind).toBe('boolean');
    expect(joinFields.find((field) => field.key === 'suffix')?.label).toBe('Right column suffix');

    const sort = getNodeDefinition('transform.sort_limit')!;
    const sortFields = fieldsFor(sort);
    expect(sortFields.find((field) => field.key === 'offset')?.kind).toBe('number');
    expect(sortFields.find((field) => field.key === 'field')?.placeholder).toBe('date desc, symbol');

    const select = getNodeDefinition('transform.select')!;
    expect(fieldsFor(select).find((field) => field.key === 'onMissing')?.options?.map((option) => option.value))
      .toEqual(['null', 'drop', 'error']);
    const rename = fieldsFor(select).find((field) => field.key === 'rename');
    expect(rename?.kind).toBe('keyvalue');
    expect(rename?.jsonString).toBe(true);

    const sortCase = sortFields.find((field) => field.key === 'caseInsensitive');
    expect(sortCase?.kind).toBe('boolean');

    const template = getNodeDefinition('transform.template')!;
    expect(fieldsFor(template).find((field) => field.key === 'template')?.kind).toBe('textarea');

    const aggregate = getNodeDefinition('logic.aggregate')!;
    const aggregateFields = fieldsFor(aggregate);
    expect(aggregateFields.find((field) => field.key === 'op')?.options?.map((option) => option.value))
      .toEqual(['sum', 'avg', 'min', 'max', 'count', 'median', 'stddev', 'percentile']);
    expect(aggregateFields.find((field) => field.key === 'percentile')).toMatchObject({
      kind: 'number',
      min: 0,
      max: 100,
    });
  });

  it('declares a control in/out on the transform and table nodes', () => {
    for (const type of [
      'transform.template', 'transform.formula', 'transform.select', 'transform.sort_limit',
      'transform.join', 'logic.aggregate', 'logic.deduplicate', 'logic.map', 'logic.filter',
      'logic.reduce', 'data.dataset.save', 'data.dataset.load',
    ]) {
      const def = getNodeDefinition(type)!;
      expect(def.inputs.find((port) => port.id === 'in')?.kind, type).toBe('control');
      expect(def.outputs.find((port) => port.id === 'done')?.kind, type).toBe('control');
    }
  });

  it('gives the branch and flow nodes a consistent control surface', () => {
    // Every logic/flow node can be gated...
    for (const type of [
      'logic.condition', 'logic.switch', 'logic.merge', 'flow.gate', 'logic.wait',
      'logic.stop', 'flow.subworkflow', 'flow.for_each', 'flow.repeat', 'flow.while',
    ]) {
      expect(getNodeDefinition(type)!.inputs.find((port) => port.id === 'in')?.kind, type).toBe('control');
    }
    // ...and everything except the branch routers and Stop can chain a `done`.
    for (const type of [
      'logic.merge', 'flow.gate', 'logic.wait', 'flow.subworkflow',
      'flow.for_each', 'flow.repeat', 'flow.while',
    ]) {
      expect(getNodeDefinition(type)!.outputs.find((port) => port.id === 'done')?.kind, type).toBe('control');
    }
    // A branch router keeps its exclusive outputs instead of a `done`.
    expect(getNodeDefinition('logic.condition')!.outputs.map((port) => port.id))
      .toEqual(['true', 'false', 'result']);
    expect(getNodeDefinition('logic.switch')!.outputs.map((port) => port.id))
      .toEqual(['matched', 'default', 'caseIndex', 'case1', 'case2', 'case3', 'case4', 'case5', 'case6', 'case7', 'case8']);
    // Merge's strategy used to render as a free-text box.
    expect(fieldsFor(getNodeDefinition('logic.merge')!).find((field) => field.key === 'strategy')?.kind)
      .toBe('select');
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
    const def = getNodeDefinition('flow.subworkflow')!;
    expect(fieldsFor(def)).toMatchObject([
      { key: 'workflowId', label: 'Workflow Id', kind: 'text' },
      { key: 'version', label: 'Version', kind: 'number' },
    ]);
    const quant = getNodeDefinition('quant.zscore')!;
    expect(fieldsFor(quant)).toMatchObject([
      { key: 'period', label: 'Period', kind: 'number', inline: true, min: 2, max: 500 },
    ]);
  });
});

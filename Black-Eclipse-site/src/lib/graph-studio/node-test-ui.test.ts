import { describe, expect, it } from 'vitest';
import { getNodeDefinition } from './registry';
import {
  canTestNode,
  canTestNodeWithNetwork,
  inputsText,
  missingRequiredInputs,
  parseNodeInputs,
} from './node-test-ui';

describe('node test UI helpers', () => {
  it('allows only safe side-effect classes', () => {
    expect(canTestNode(getNodeDefinition('trigger.manual')!)).toBe(true);
    expect(canTestNode(getNodeDefinition('transform.formula')!)).toBe(true);
    expect(canTestNode(getNodeDefinition('finance.market_data')!)).toBe(true);
    expect(canTestNode(getNodeDefinition('integration.http')!)).toBe(false);
    expect(canTestNode(getNodeDefinition('agent.research')!)).toBe(false);
    expect(canTestNode(getNodeDefinition('flow.subworkflow')!)).toBe(false);
  });

  it('offers network nodes only through the explicit confirmation path', () => {
    expect(canTestNodeWithNetwork(getNodeDefinition('integration.http')!)).toBe(true);
    expect(canTestNodeWithNetwork(getNodeDefinition('integration.webhook_send')!)).toBe(true);
    expect(canTestNodeWithNetwork(getNodeDefinition('file.write')!)).toBe(false);
    expect(canTestNodeWithNetwork(getNodeDefinition('trigger.manual')!)).toBe(false);
  });

  it('parses inputs as a JSON object', () => {
    expect(parseNodeInputs('')).toEqual({ ok: true, value: {} });
    expect(parseNodeInputs('{"x": 3}')).toEqual({ ok: true, value: { x: 3 } });
    expect(parseNodeInputs('[]').ok).toBe(false);
    expect(parseNodeInputs('{bad}').ok).toBe(false);
  });

  it('reports missing required ports and ignores optional ones', () => {
    const formula = getNodeDefinition('transform.formula')!;
    expect(missingRequiredInputs(formula, {})).toEqual(['x']);
    expect(missingRequiredInputs(formula, { x: 1 })).toEqual([]);

    const value = getNodeDefinition('data.value')!;
    // `in` is optional.
    expect(missingRequiredInputs(value, {})).toEqual([]);
  });

  it('renders empty input maps as an empty object', () => {
    expect(inputsText(null)).toBe('{}');
    expect(inputsText({})).toBe('{}');
    expect(inputsText({ x: 1 })).toBe('{\n  "x": 1\n}');
  });
});

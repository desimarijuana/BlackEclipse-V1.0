import { describe, expect, it } from 'vitest';
import { createWorkflowIR } from './ir';
import { portsCompatible, validateWorkflow } from './validation';
import { buildTemplate, WORKFLOW_TEMPLATES } from './templates';
import { getNodeDefinition } from './registry';
import type { PortDef, WorkflowIR } from './types';

function port(partial: Partial<PortDef> & Pick<PortDef, 'type'>): PortDef {
  return { id: partial.id ?? 'p', name: partial.name ?? 'P', kind: partial.kind ?? 'data', ...partial };
}

function node(ir: WorkflowIR, type: string, id: string) {
  const def = getNodeDefinition(type)!;
  return { id, type, version: def.version, config: def.defaultConfig(), layout: { x: 0, y: 0 } };
}

describe('port compatibility', () => {
  it('allows any ↔ anything', () => {
    expect(portsCompatible(port({ type: 'any' }), port({ type: 'number' }))).toBe(true);
    expect(portsCompatible(port({ type: 'string' }), port({ type: 'any' }))).toBe(true);
  });
  it('requires exact data type match', () => {
    expect(portsCompatible(port({ type: 'number' }), port({ type: 'string' }))).toBe(false);
    expect(portsCompatible(port({ type: 'ohlcv' }), port({ type: 'ohlcv' }))).toBe(true);
  });
  it('keeps control ports separate from data ports', () => {
    expect(portsCompatible(port({ type: 'any', kind: 'control' }), port({ type: 'any' }))).toBe(false);
    expect(portsCompatible(port({ type: 'any', kind: 'control' }), port({ type: 'any', kind: 'control' }))).toBe(true);
  });
});

describe('workflow validation', () => {
  it('accepts every starter template', () => {
    for (const template of WORKFLOW_TEMPLATES) {
      const ir = buildTemplate(template.id)!;
      const errors = validateWorkflow(ir).filter((d) => d.severity === 'error');
      expect(errors, template.id).toEqual([]);
    }
  });

  it('reports a missing trigger and terminal on an empty graph', () => {
    const ir = createWorkflowIR({ nodes: [node(createWorkflowIR(), 'transform.template', 't')] });
    const codes = validateWorkflow(ir).map((d) => d.code);
    expect(codes).toContain('missing_trigger');
    expect(codes).toContain('missing_terminal');
  });

  it('reports incompatible port connections', () => {
    const base = createWorkflowIR();
    const ir: WorkflowIR = {
      ...base,
      nodes: [node(base, 'trigger.manual', 'trig'), node(base, 'finance.indicator', 'ind')],
      edges: [{ id: 'e1', source: 'trig', sourceHandle: 'start', target: 'ind', targetHandle: 'series' }],
    };
    // trigger.start is `any` → allowed; force an incompatible edge explicitly:
    const bad: WorkflowIR = {
      ...ir,
      edges: [{ id: 'e1', source: 'ind', sourceHandle: 'values', target: 'trig', targetHandle: 'nope' }],
    };
    expect(validateWorkflow(bad).map((d) => d.code)).toContain('invalid_edge_handles');
  });

  it('reports a missing required input', () => {
    const base = createWorkflowIR();
    const ir: WorkflowIR = {
      ...base,
      nodes: [node(base, 'trigger.manual', 'trig'), node(base, 'output.result', 'out')],
      edges: [],
    };
    const codes = validateWorkflow(ir).map((d) => d.code);
    expect(codes).toContain('missing_required_input');
  });

  it('detects cycles', () => {
    const base = createWorkflowIR();
    const a = node(base, 'logic.merge', 'a');
    const b = node(base, 'logic.merge', 'b');
    const ir: WorkflowIR = {
      ...base,
      nodes: [a, b],
      edges: [
        { id: 'e1', source: 'a', sourceHandle: 'value', target: 'b', targetHandle: 'a' },
        { id: 'e2', source: 'b', sourceHandle: 'value', target: 'a', targetHandle: 'a' },
      ],
    };
    expect(validateWorkflow(ir).map((d) => d.code)).toContain('illegal_cycle');
  });

  it('reports invalid config', () => {
    const base = createWorkflowIR();
    const bad = { ...node(base, 'finance.indicator', 'ind'), config: { kind: 'not-real', period: 20 } };
    const ir: WorkflowIR = { ...base, nodes: [node(base, 'trigger.manual', 'trig'), bad] };
    expect(validateWorkflow(ir).map((d) => d.code)).toContain('invalid_config');
  });
});

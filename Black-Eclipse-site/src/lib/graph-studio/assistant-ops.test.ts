import { describe, expect, it } from 'vitest';
import { describeOp, graphEditOpsToPatches, type GraphEditOp } from './assistant-ops';

describe('graphEditOpsToPatches', () => {
  it('maps an add_node operation with a layout', () => {
    const patches = graphEditOpsToPatches([
      {
        op: 'add_node',
        node: {
          id: 'n_filter',
          type: 'logic.filter',
          version: '1.0.0',
          label: 'Filter rows',
          config: { expression: 'value > 0' },
          layout: { x: 240, y: 80 },
        },
      },
    ]);
    expect(patches).toEqual([
      {
        op: 'add_node',
        node: {
          id: 'n_filter',
          type: 'logic.filter',
          version: '1.0.0',
          label: 'Filter rows',
          config: { expression: 'value > 0' },
          layout: { x: 240, y: 80 },
        },
      },
    ]);
  });

  it('defaults a missing layout instead of inventing a position from the registry', () => {
    const [patch] = graphEditOpsToPatches([
      { op: 'add_node', node: { type: 'logic.map', version: '1.0.0' } },
    ]);
    expect(patch).toMatchObject({ op: 'add_node', node: { layout: { x: 120, y: 100 }, config: {} } });
  });

  it('maps wiring, config, labels, removal and workflow metadata', () => {
    const ops: GraphEditOp[] = [
      { op: 'add_edge', edge: { source: 'a', sourceHandle: 'items', target: 'b', targetHandle: 'items' } },
      { op: 'remove_edge', edgeId: 'e1' },
      { op: 'update_node_config', nodeId: 'b', config: { expression: 'x' } },
      { op: 'update_node_label', nodeId: 'b', label: null },
      { op: 'remove_node', nodeId: 'c' },
      { op: 'set_settings', settings: { executionMode: 'paper' } },
      { op: 'set_meta', name: 'Renamed' },
    ];
    expect(graphEditOpsToPatches(ops)).toEqual([
      {
        op: 'add_edge',
        edge: { source: 'a', sourceHandle: 'items', target: 'b', targetHandle: 'items' },
      },
      { op: 'remove_edge', edgeId: 'e1' },
      { op: 'update_node_config', nodeId: 'b', config: { expression: 'x' } },
      { op: 'update_node_label', nodeId: 'b', label: undefined },
      { op: 'remove_node', nodeId: 'c' },
      { op: 'set_settings', settings: { executionMode: 'paper' } },
      { op: 'set_meta', name: 'Renamed' },
    ]);
  });

  it('describes operations for the proposal card', () => {
    expect(describeOp({ op: 'add_node', node: { type: 'logic.filter', version: '1' } })).toBe('Add logic.filter');
    expect(describeOp({ op: 'add_edge', edge: { source: 'a', sourceHandle: 'x', target: 'b', targetHandle: 'y' } }))
      .toBe('Connect a → b');
  });
});

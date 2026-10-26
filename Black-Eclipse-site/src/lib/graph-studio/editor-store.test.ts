import { beforeEach, describe, expect, it } from 'vitest';
import { useGraphEditor } from './editor-store';
import { buildTemplate } from './templates';

const store = () => useGraphEditor.getState();

describe('graph editor store', () => {
  beforeEach(() => {
    store().reset();
  });

  it('loads a workflow and clears the dirty flag', () => {
    const ir = buildTemplate('blank')!;
    store().load(ir, { workflowId: 'w1', baseVersion: 3 });
    expect(store().ir?.name).toBe(ir.name);
    expect(store().dirty).toBe(false);
    expect(store().baseVersion).toBe(3);
  });

  it('applies a valid patch and marks dirty', () => {
    const ir = buildTemplate('blank')!;
    store().load(ir, { workflowId: 'w1' });
    const ok = store().dispatch({ op: 'set_meta', name: 'Renamed' });
    expect(ok).toBe(true);
    expect(store().ir?.name).toBe('Renamed');
    expect(store().dirty).toBe(true);
    expect(store().past.length).toBe(1);
  });

  it('undo / redo restores the previous document', () => {
    const ir = buildTemplate('blank')!;
    store().load(ir, { workflowId: 'w1' });
    store().dispatch({ op: 'set_meta', name: 'Renamed' });
    store().undo();
    expect(store().ir?.name).toBe(ir.name);
    store().redo();
    expect(store().ir?.name).toBe('Renamed');
  });

  it('a rejected patch changes nothing and records the error', () => {
    const ir = buildTemplate('blank')!;
    store().load(ir, { workflowId: 'w1' });
    const before = store().ir;
    const ok = store().dispatch({ op: 'remove_node', nodeId: 'does-not-exist' });
    expect(ok).toBe(false);
    expect(store().ir).toBe(before);
    expect(store().lastError).toBeTruthy();
    expect(store().dirty).toBe(false);
  });

  it('holds the displayed run transiently and clears it on load', () => {
    const ir = buildTemplate('blank')!;
    store().load(ir, { workflowId: 'w1' });
    store().setRun({
      id: 'grun_1', workflowId: 'w1', irVersion: 1, mode: 'research', testRun: true,
      status: 'succeeded', startedAt: '2026-01-01T00:00:00Z',
    });
    expect(store().run?.id).toBe('grun_1');
    // A run is NOT part of the document: loading another workflow drops it.
    store().load(ir, { workflowId: 'w2' });
    expect(store().run).toBeNull();
  });

  it('markSaved clears dirty and records the version', () => {
    const ir = buildTemplate('blank')!;
    store().load(ir, { workflowId: 'w1' });
    store().dispatch({ op: 'set_meta', name: 'Renamed' });
    store().markSaved(5, 'wf_abc');
    expect(store().dirty).toBe(false);
    expect(store().baseVersion).toBe(5);
    expect(store().serverContentHash).toBe('wf_abc');
  });

  it('duplicates and pastes selections through the same patch chokepoint', () => {
    const ir = buildTemplate('blank')!;
    store().load(ir, { workflowId: 'w1' });
    store().selectAll();
    expect(store().duplicateSelection()).toBe(true);
    expect(store().ir?.nodes).toHaveLength(4);
    expect(store().selection.nodeIds).toHaveLength(2);

    store().selectAll();
    expect(store().copySelection()).toBe(true);
    expect(store().pasteClipboard()).toBe(true);
    expect(store().ir?.nodes).toHaveLength(8);
    expect(store().past.length).toBe(2);
  });

  it('increments loadNonce so the workspace can open the editor', () => {
    const ir = buildTemplate('blank')!;
    const before = store().loadNonce;
    store().load(ir, { workflowId: 'w1' });
    expect(store().loadNonce).toBe(before + 1);
  });
});

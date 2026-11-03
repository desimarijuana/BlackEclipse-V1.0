import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { buildTemplate } from './templates';
import { useGraphEditor } from './editor-store';
import { useGraphAssistant } from './assistant-store';

function respond(body: unknown) {
  const events = [
    { type: 'status', stage: 'thinking', label: 'Thinking…' },
    { type: 'tool_start', name: 'add_node', label: 'Adding logic.filter' },
    { type: 'tool_end', name: 'add_node', label: 'Adding logic.filter', ok: true },
    { type: 'result', result: body },
  ];
  const text = events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join('');
  return new Response(text, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  });
}

function proposal(overrides: Record<string, unknown> = {}) {
  return {
    ok: true,
    mode: 'edit',
    answer: 'Added a filter.',
    summary: 'Added a filter.',
    ops: [
      {
        op: 'add_node',
        node: { id: 'n_filter', type: 'logic.filter', version: '1.0.0', config: {}, layout: { x: 120, y: 100 } },
      },
    ],
    diagnostics: [],
    errors: [],
    warnings: [],
    focusNodeIds: ['n_filter'],
    model: { provider: 'test', model: 'test' },
    ...overrides,
  };
}

const editor = () => useGraphEditor.getState();
const assistant = () => useGraphAssistant.getState();

describe('graph assistant store', () => {
  beforeEach(() => {
    editor().reset();
    assistant().reset();
    editor().load(buildTemplate('blank')!, { workflowId: 'w1', baseVersion: 1 });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('auto-applies a safe edit as one undo step', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => respond(proposal())));
    await assistant().send('Add a filter');

    expect(editor().ir?.nodes.some((node) => node.id === 'n_filter')).toBe(true);
    expect(assistant().pending).toBeNull();
    expect(assistant().messages.at(-1)?.applied).toBe(true);
    expect(editor().past).toHaveLength(1);

    editor().undo();
    expect(editor().ir?.nodes.some((node) => node.id === 'n_filter')).toBe(false);
  });

  it('keeps a proposal with warnings for review, then applies it on request', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => respond(proposal({ warnings: ['Trading nodes require paper mode.'] }))));
    await assistant().send('Add a filter');

    expect(assistant().pending).not.toBeNull();
    expect(editor().ir?.nodes.some((node) => node.id === 'n_filter')).toBe(false);
    expect(assistant().messages.at(-1)?.pending).toBe(true);

    expect(assistant().applyPending()).toBe(true);
    expect(editor().ir?.nodes.some((node) => node.id === 'n_filter')).toBe(true);
    expect(assistant().messages.at(-1)?.applied).toBe(true);
  });

  it('honours the auto-apply preference', async () => {
    assistant().setAutoApply(false);
    vi.stubGlobal('fetch', vi.fn(async () => respond(proposal())));
    await assistant().send('Add a filter');

    expect(assistant().pending).not.toBeNull();
    expect(editor().ir?.nodes.some((node) => node.id === 'n_filter')).toBe(false);
  });

  it('discards a proposal without touching the graph', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => respond(proposal({ warnings: ['Review this.'] }))));
    await assistant().send('Add a filter');
    assistant().discardPending();

    expect(assistant().pending).toBeNull();
    expect(editor().ir?.nodes.some((node) => node.id === 'n_filter')).toBe(false);
  });
});

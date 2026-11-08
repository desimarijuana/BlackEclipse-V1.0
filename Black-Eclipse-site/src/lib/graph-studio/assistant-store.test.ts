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

  it('routes pause and resume to the live run endpoints', async () => {
    const fetchMock = vi.fn(async () => new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    useGraphAssistant.setState({ runId: 'assist_test', status: 'running' });

    await assistant().pause();
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/graphs/assist/runs/assist_test/pause',
      expect.objectContaining({ method: 'POST' }),
    );
    expect(assistant().status).toBe('paused');

    await assistant().resume();
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/graphs/assist/runs/assist_test/resume',
      expect.objectContaining({ method: 'POST' }),
    );
    expect(assistant().status).toBe('running');
  });

  it('records the approval decision before applying the proposal', async () => {
    const fetchMock = vi.fn(async () => new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    const result = proposal({
      approval: {
        id: 'appr_1',
        kind: 'graph_edit',
        status: 'pending',
        title: 'Apply this change?',
        summary: 'Apply one change.',
        effect: 'write',
        risk: 'low',
        grantPattern: 'graph_edit:w1',
      },
    });
    useGraphAssistant.setState({
      pending: result as never,
      pendingDocumentId: editor().ir?.id ?? null,
      autoApply: false,
    });

    await assistant().decidePending(true, false);

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/harness/mcp/approvals/appr_1/decide',
      expect.objectContaining({ method: 'POST' }),
    );
    expect(editor().ir?.nodes.some((node) => node.id === 'n_filter')).toBe(true);
  });

  it('folds streamed text deltas into one assistant message', async () => {
    const events = [
      { type: 'run', runId: 'assist_stream' },
      { type: 'text_delta', text: 'Hel' },
      { type: 'text_delta', text: 'lo' },
      {
        type: 'result',
        result: {
          ...proposal({ summary: 'Hello', answer: 'Hello', ops: [], mode: 'ask' }),
        },
      },
    ];
    const text = events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join('');
    vi.stubGlobal('fetch', vi.fn(async () => new Response(text, {
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
    })));

    await assistant().send('Say hello', 'ask');

    const last = assistant().messages.at(-1);
    expect(last?.role).toBe('assistant');
    expect(last?.content).toBe('Hello');
    expect(last?.streaming).toBe(false);
    expect(assistant().messages.filter((message) => message.role === 'assistant')).toHaveLength(1);
  });
});

import { describe, expect, it } from 'vitest';
import { normalizeHarnessEvent, unwrapEventPayload } from './events';
import { toolLabel, sourceLabel, turnText, emptyTurn } from './response-model';

describe('unwrapEventPayload', () => {
  it('unwraps a runtime envelope and carries the event type', () => {
    const out = unwrapEventPayload({
      id: 'evt_1',
      runId: 'run_1',
      type: 'model.delta',
      seq: 3,
      data: { text: 'hello' },
    });
    expect(out.text).toBe('hello');
    expect(out.eventType).toBe('model.delta');
  });

  it('passes a flat client frame through unchanged', () => {
    const out = unwrapEventPayload({ runId: 'run_1', output: 'done' });
    expect(out.output).toBe('done');
    expect(out.eventType).toBeUndefined();
  });
});

describe('normalizeHarnessEvent', () => {
  it('maps model.delta text to a delta event', () => {
    const e = normalizeHarnessEvent('model.delta', {
      type: 'model.delta',
      data: { text: 'NVDA ' },
    });
    expect(e).toEqual({ kind: 'delta', text: 'NVDA ' });
  });

  it('ignores an empty delta', () => {
    expect(normalizeHarnessEvent('model.delta', { data: { text: '' } })).toBeNull();
  });

  it('maps tool.requested to a human-labeled activity_start', () => {
    const e = normalizeHarnessEvent('tool.requested', {
      type: 'tool.requested',
      data: { name: 'market_get_quote', toolCallId: 'call_1' },
    });
    expect(e).toMatchObject({
      kind: 'activity_start',
      item: { id: 'call_1', name: 'market_get_quote', status: 'running', kind: 'tool' },
    });
    if (e?.kind === 'activity_start') {
      expect(e.item.label).toBe('Retrieving market quote');
    }
  });

  it('correlates tool.completed by toolCallId', () => {
    const e = normalizeHarnessEvent('tool.completed', {
      type: 'tool.completed',
      data: { name: 'market_get_quote', toolCallId: 'call_1', durationMs: 120 },
    });
    expect(e).toEqual({
      kind: 'activity_end',
      id: 'call_1',
      name: 'market_get_quote',
      status: 'completed',
      durationMs: 120,
      code: undefined,
    });
  });

  it('surfaces tool.failed as a failed activity with its code', () => {
    const e = normalizeHarnessEvent('tool.failed', {
      type: 'tool.failed',
      data: { name: 'research_search', toolCallId: 'call_2', code: 'TOOL_ERROR' },
    });
    expect(e).toMatchObject({ kind: 'activity_end', status: 'failed', code: 'TOOL_ERROR' });
  });

  it('maps retrieval source events, falling back to a composite id', () => {
    const start = normalizeHarnessEvent('retrieval.source_start', {
      type: 'retrieval.source_start',
      data: { source: 'yfinance', dataType: 'quote' },
    });
    expect(start).toMatchObject({
      kind: 'activity_start',
      item: { id: 'retrieval:yfinance:quote', kind: 'retrieval', name: 'yfinance' },
    });
    if (start?.kind === 'activity_start') {
      expect(start.item.label).toBe('Consulting Yahoo Finance');
    }

    const ok = normalizeHarnessEvent('retrieval.source_ok', {
      type: 'retrieval.source_ok',
      data: { source: 'yfinance', dataType: 'quote' },
    });
    expect(ok).toMatchObject({
      kind: 'activity_end',
      id: 'retrieval:yfinance:quote',
      status: 'completed',
    });
  });

  it('reports a retrieval record count only when the runtime sends one', () => {
    const withCount = normalizeHarnessEvent('retrieval.source_ok', {
      type: 'retrieval.source_ok',
      data: { source: 'jdds', dataType: 'quote', objects: 3 },
    });
    expect(withCount).toMatchObject({ kind: 'activity_end', summary: '3 records' });

    const one = normalizeHarnessEvent('retrieval.source_ok', {
      type: 'retrieval.source_ok',
      data: { source: 'jdds', dataType: 'quote', objects: 1 },
    });
    expect(one).toMatchObject({ kind: 'activity_end', summary: '1 record' });

    const unknown = normalizeHarnessEvent('retrieval.source_ok', {
      type: 'retrieval.source_ok',
      data: { source: 'jdds', dataType: 'quote' },
    });
    expect((unknown as { summary?: string }).summary).toBeUndefined();
  });

  it('maps client.final to the authoritative output', () => {
    const e = normalizeHarnessEvent('client.final', { runId: 'r', status: 'completed', output: 'Answer' });
    expect(e).toEqual({
      kind: 'final',
      output: 'Answer',
      error: undefined,
      status: 'completed',
      research: undefined,
      memory: undefined,
      runId: 'r',
    });
  });

  it('carries Phase 4 research metadata on client.final', () => {
    const research = { status: 'partial', metadata: { limitations: ['x'] } };
    const e = normalizeHarnessEvent('client.final', {
      runId: 'r',
      status: 'completed',
      output: 'Answer',
      research,
    });
    expect(e).toMatchObject({ kind: 'final', research });
  });

  it('maps run.failed to an error with code', () => {
    const e = normalizeHarnessEvent('run.failed', {
      type: 'run.failed',
      data: { error: { code: 'PROVIDER_ERROR', message: 'boom' } },
    });
    expect(e).toEqual({ kind: 'error', message: 'boom', code: 'PROVIDER_ERROR' });
  });

  it('maps lifecycle events to coarse status', () => {
    expect(normalizeHarnessEvent('run.started', { type: 'run.started', data: {} })).toEqual({
      kind: 'status',
      status: 'planning',
    });
    expect(normalizeHarnessEvent('run.completed', { type: 'run.completed', data: {} })).toEqual({
      kind: 'status',
      status: 'completed',
    });
    expect(normalizeHarnessEvent('run.cancelled', { type: 'run.cancelled', data: {} })).toEqual({
      kind: 'status',
      status: 'cancelled',
    });
  });

  it('surfaces a history trim as one bounded activity line (counts only)', () => {
    const e = normalizeHarnessEvent('memory.history_bounded', {
      type: 'memory.history_bounded',
      data: {
        keptTurns: 20,
        droppedTurns: 10,
        droppedTokensEstimate: 5000,
        window: 32000,
        windowKnown: true,
        tighterRetry: false,
      },
    });
    expect(e).toMatchObject({
      kind: 'activity_start',
      item: { id: 'history_bounded', kind: 'bounded', status: 'completed' },
    });
    if (e?.kind === 'activity_start') {
      expect(e.item.label).toContain('Trimmed 10 older turns');
      expect(e.item.summary).toContain('20 kept');
      expect(e.item.summary).toContain('32,000-token window');
    }
  });

  it('reports an unknown window honestly on the bounded line', () => {
    const e = normalizeHarnessEvent('memory.history_bounded', {
      type: 'memory.history_bounded',
      data: { keptTurns: 20, droppedTurns: 10, window: null, windowKnown: false },
    });
    if (e?.kind === 'activity_start') {
      expect(e.item.summary).toContain('context window unknown');
    } else {
      throw new Error('expected an activity_start');
    }
  });

  it('emits nothing for a history_bounded with no dropped turns', () => {
    expect(
      normalizeHarnessEvent('memory.history_bounded', {
        type: 'memory.history_bounded',
        data: { keptTurns: 5, droppedTurns: 0, window: 32000, windowKnown: true },
      }),
    ).toBeNull();
  });

  it('surfaces memory recall as one recall activity line (counts only)', () => {
    const e = normalizeHarnessEvent('memory.retrieved', {
      type: 'memory.retrieved',
      data: {
        selected: 3,
        candidates: 12,
        usedChars: 2400,
        budgetChars: 4000,
        // The full payload the runtime sends — none of this may reach the line.
        selectedIds: ['mem_secret_1', 'mem_secret_2'],
        excluded: [{ id: 'mem_no', reason: 'scope mismatch' }],
        selectionReasons: [{ id: 'mem_secret_1', reason: 'topic match' }],
      },
    });
    expect(e).toMatchObject({
      kind: 'activity_start',
      item: { id: 'memory_recalled', kind: 'recall', status: 'completed' },
    });
    if (e?.kind === 'activity_start') {
      expect(e.item.label).toBe('Recalled 3 memories from long-term memory');
      expect(e.item.summary).toBe('2,400 chars recalled');
      // Never memory content, ids or excluded text.
      const surface = `${e.item.label} ${e.item.summary ?? ''}`;
      expect(surface).not.toContain('mem_secret');
      expect(surface).not.toContain('scope mismatch');
    }
  });

  it('uses the singular form for a single recalled memory', () => {
    const e = normalizeHarnessEvent('memory.retrieved', {
      type: 'memory.retrieved',
      data: { selected: 1, usedChars: 90 },
    });
    if (e?.kind === 'activity_start') {
      expect(e.item.label).toBe('Recalled 1 memory from long-term memory');
    } else {
      throw new Error('expected an activity_start');
    }
  });

  it('emits nothing when no memory was recalled', () => {
    expect(
      normalizeHarnessEvent('memory.retrieved', {
        type: 'memory.retrieved',
        data: { selected: 0, usedChars: 0 },
      }),
    ).toBeNull();
    expect(normalizeHarnessEvent('memory.retrieved', { type: 'memory.retrieved', data: {} })).toBeNull();
  });

  it('returns null (never throws) for a malformed memory.retrieved payload', () => {
    expect(
      normalizeHarnessEvent('memory.retrieved', {
        type: 'memory.retrieved',
        data: { selected: 'lots', usedChars: null },
      }),
    ).toBeNull();
  });

  it('maps a CONTEXT_OVERFLOW run.failed with its specific message', () => {
    const e = normalizeHarnessEvent('run.failed', {
      type: 'run.failed',
      data: {
        error: {
          code: 'CONTEXT_OVERFLOW',
          message: 'The request exceeded the model\'s context window. Start a shorter conversation.',
        },
      },
    });
    expect(e).toMatchObject({ kind: 'error', code: 'CONTEXT_OVERFLOW' });
    if (e?.kind === 'error') expect(e.message).toContain('shorter conversation');
  });
});

describe('response-model helpers', () => {
  it('prefers finalText over streamed text', () => {
    expect(turnText({ ...emptyTurn(), text: 'partial', finalText: 'final' })).toBe('final');
    expect(turnText({ ...emptyTurn(), text: 'partial' })).toBe('partial');
  });

  it('prettifies unknown tool names instead of leaking snake_case', () => {
    expect(toolLabel('some_unknown_thing')).toBe('Using some unknown thing');
  });

  it('labels known sources and passes unknown ones through', () => {
    expect(sourceLabel('jdds')).toBe('market data');
    expect(sourceLabel('custom-vendor')).toBe('custom-vendor');
  });
});

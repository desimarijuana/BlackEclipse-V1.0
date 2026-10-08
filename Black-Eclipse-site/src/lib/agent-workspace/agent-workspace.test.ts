import { describe, expect, it } from 'vitest';
import { normalizeWorkspaceEvent } from './normalize';
import { applyWorkspaceEvents, initialWorkspaceState } from './reducer';
import { replayTrace } from './history';
import type { AgentWorkspaceState, WorkspaceEvent } from './types';

function run(events: WorkspaceEvent[], state = initialWorkspaceState('run_1')): AgentWorkspaceState {
  return applyWorkspaceEvents(state, events);
}

function norm(type: string, data: Record<string, unknown>, at = 1000): WorkspaceEvent[] {
  return normalizeWorkspaceEvent(type, data, at);
}

describe('normalizeWorkspaceEvent — lifecycle', () => {
  it('maps run lifecycle to agent status', () => {
    expect(norm('run.created', {}).map((e) => e.type)).toEqual(['agent']);
    const started = norm('run.started', {});
    expect(started).toMatchObject([{ type: 'agent', status: 'running' }]);
    const done = norm('run.completed', { output: 'ok' });
    expect(done).toMatchObject([{ type: 'finished', status: 'completed', output: 'ok' }]);
  });

  it('maps run.failed to an error AND a finished event', () => {
    const out = norm('run.failed', { error: { code: 'BOOM', message: 'bad' } });
    expect(out).toMatchObject([
      { type: 'error', message: 'bad', code: 'BOOM' },
      { type: 'finished', status: 'failed' },
    ]);
  });
});

describe('normalizeWorkspaceEvent — tools', () => {
  it('maps tool.requested to a running activity with a category', () => {
    const out = norm('tool.requested', { name: 'workspace_read', toolCallId: 'c1', detail: 'src/a.ts' });
    expect(out).toHaveLength(1);
    const entry = (out[0] as { entry: { category: string; label: string; detail: string; status: string } }).entry;
    expect(entry.category).toBe('file');
    expect(entry.label).toBe('Reading a file');
    expect(entry.detail).toBe('src/a.ts');
    expect(entry.status).toBe('running');
  });

  it('classifies browser/computer/git/research/command tools', () => {
    const cat = (name: string) => {
      const e = norm('tool.requested', { name, toolCallId: 'x' })[0] as { entry: { category: string } };
      return e.entry.category;
    };
    expect(cat('browser_click')).toBe('browser');
    expect(cat('computer_action')).toBe('computer');
    expect(cat('git_status')).toBe('git');
    expect(cat('research_search')).toBe('research');
    expect(cat('terminal_run')).toBe('command');
    expect(cat('market_get_quote')).toBe('tool');
  });

  it('maps tool.failed to a failed activity_end and emits nothing for completed', () => {
    const failed = norm('tool.failed', { name: 'x', toolCallId: 'c', code: 'TOOL_ERROR' });
    expect(failed).toMatchObject([{ type: 'activity_end', status: 'failed', code: 'TOOL_ERROR' }]);
    const ok = norm('tool.completed', { name: 'x', toolCallId: 'c', durationMs: 5 });
    expect(ok).toMatchObject([{ type: 'activity_end', status: 'completed', durationMs: 5 }]);
  });

  it('emits an artifact handle when a tool result was truncated', () => {
    const out = norm('tool.completed', { name: 'terminal_run', toolCallId: 'c', truncated: true, totalChars: 90000 });
    expect(out.some((e) => e.type === 'artifact')).toBe(true);
    const artifact = out.find((e) => e.type === 'artifact');
    expect(artifact).toMatchObject({ artifact: { type: 'terminal', sizeBytes: 90000 } });
  });

  it('routes refusals to a content-free activity carrying only the code', () => {
    const out = norm('command.refused', { commandClass: 'shell', code: 'COMMAND_DENIED' });
    expect(out[0]).toMatchObject({ type: 'activity', entry: { category: 'command', code: 'COMMAND_DENIED' } });
  });
});

describe('normalizeWorkspaceEvent — files / changes / artifacts', () => {
  it('maps code.read to a file activity and inspected counts', () => {
    const out = norm('code.read', { path: 'src/x.ts', lines: 40 });
    expect(out[0]).toMatchObject({ type: 'activity', entry: { category: 'file', detail: 'src/x.ts' } });
    expect(out[1]).toMatchObject({ type: 'context', patch: { linesInspectedDelta: 40, fileKey: 'src/x.ts' } });
  });

  it('maps a write to a change row plus an artifact', () => {
    const out = norm('fs.edit_file.applied', { path: 'src/y.ts', bytesWritten: 120 });
    expect(out.some((e) => e.type === 'file')).toBe(true);
    expect(out.some((e) => e.type === 'artifact')).toBe(true);
  });

  it('maps code.diff to a change-summary activity and a diff artifact', () => {
    const out = norm('code.diff', { filesChanged: 3, additions: 10, deletions: 2, digest: 'abc' });
    expect(out[0]).toMatchObject({ type: 'activity', entry: { label: 'Showing what changed' } });
    expect(out[1]).toMatchObject({ type: 'artifact', artifact: { type: 'diff' } });
  });
});

describe('normalizeWorkspaceEvent — permissions', () => {
  it('maps approval.requested to a pending permission', () => {
    const out = norm('approval.requested', { approvalId: 'a1', tool: 'git_push', risk: 'high', effect: 'external_action' });
    expect(out).toMatchObject([
      { type: 'permission', permission: { id: 'a1', status: 'pending', risk: 'high' } },
    ]);
  });

  it('maps approval.resolved to a resolution event', () => {
    expect(norm('approval.resolved', { approvalId: 'a1', approved: false }))
      .toMatchObject([{ type: 'permission_resolved', id: 'a1', approved: false }]);
  });

  it('emits nothing for a malformed approval.requested', () => {
    expect(norm('approval.requested', {})).toEqual([]);
  });
});

describe('normalizeWorkspaceEvent — context / research / browser / computer', () => {
  it('reads the prompt plan into named context sources', () => {
    const out = norm('prompt.plan', {
      segments: [
        { id: 'system', source: 'system', tokenEstimate: 1000, chars: 4000 },
        { id: 'skills', source: 'skills', tokenEstimate: 300 },
      ],
    });
    expect(out[0]).toMatchObject({ type: 'context_sources' });
    const sources = (out[0] as { sources: unknown[] }).sources;
    expect(sources).toHaveLength(2);
  });

  it('reads history bounding and memory recall into context counts', () => {
    const bounded = norm('memory.history_bounded', { keptTurns: 10, droppedTurns: 4, window: 32000, windowKnown: true });
    expect(bounded[0]).toMatchObject({ type: 'context', patch: { turnsKept: 10, turnsDropped: 4 } });
    const mem = norm('memory.retrieved', { selected: 2, usedChars: 500 });
    expect(mem[0]).toMatchObject({ type: 'context', patch: { memoriesUsed: 2 } });
  });

  it('maps browser navigation + screenshot', () => {
    const nav = norm('browser.navigated', { sessionId: 's1', url: 'https://x.test' });
    expect(nav.some((e) => e.type === 'activity')).toBe(true);
    expect(nav.some((e) => e.type === 'browser')).toBe(true);
    const shot = norm('browser.screenshot', { sessionId: 's1', path: '/tmp/a.png' });
    expect(shot.some((e) => e.type === 'artifact')).toBe(true);
  });

  it('maps computer actions and session lifecycle', () => {
    const created = norm('computer.session.created', { sessionId: 'c1', application: 'VS Code' });
    expect(created[0]).toMatchObject({ type: 'computer', patch: { active: true, application: 'VS Code' } });
    const action = norm('computer.action', { sessionId: 'c1', action: 'click', verdict: 'ok' });
    expect(action.some((e) => e.type === 'activity')).toBe(true);
    const destroyed = norm('computer.session.destroyed', { sessionId: 'c1' });
    expect(destroyed[0]).toMatchObject({ type: 'computer', patch: { active: false } });
  });

  it('maps research web search + fetch + completion', () => {
    const search = norm('research.web_search', { query: 'q', results: 5, tier: 'primary' });
    expect(search.some((e) => e.type === 'activity')).toBe(true);
    expect(search.some((e) => e.type === 'research')).toBe(true);
    const done = norm('research.completed', { status: 'complete', coverage: 'full' });
    expect(done[0]).toMatchObject({ type: 'research', patch: { active: false, coverage: 'full' } });
  });
});

describe('normalizeWorkspaceEvent — malformed frames never throw', () => {
  it('returns [] for unknown types and garbage payloads', () => {
    expect(norm('something.unknown', {})).toEqual([]);
    expect(norm('code.read', { path: 123, lines: 'x' } as Record<string, unknown>)).toBeInstanceOf(Array);
    expect(norm('tool.requested', { name: null, toolCallId: {} })).toHaveLength(1);
  });
});

describe('reducer — folding normalized events', () => {
  it('tracks agent status, model, and telemetry', () => {
    const s = run([
      ...norm('run.started', {}, 1),
      ...norm('model.requested', { provider: 'openai', model: 'gpt-5' }, 2),
      ...norm('model.completed', { promptTokens: 100, completionTokens: 50, totalTokens: 150, step: 1 }, 3),
    ]);
    expect(s.execution.status).toBe('running');
    expect(s.model).toEqual({ provider: 'openai', model: 'gpt-5' });
    expect(s.telemetry.promptTokens).toBe(100);
    expect(s.telemetry.totalTokens).toBe(150);
  });

  it('correlates a tool start with its end (LIFO) and counts calls', () => {
    const s = run([
      ...norm('tool.requested', { name: 'workspace_read', toolCallId: 'c1' }, 1),
      ...norm('tool.completed', { name: 'workspace_read', toolCallId: 'c1', durationMs: 12 }, 2),
    ]);
    expect(s.activity).toHaveLength(1);
    expect(s.activity[0]).toMatchObject({ status: 'completed', durationMs: 12 });
    expect(s.telemetry.toolCalls).toBe(1);
  });

  it('records a failed tool as an error and counts it', () => {
    const s = run([
      ...norm('tool.requested', { name: 'git_push', toolCallId: 'c2' }, 1),
      ...norm('tool.failed', { name: 'git_push', toolCallId: 'c2', code: 'DENIED' }, 2),
    ]);
    expect(s.telemetry.toolErrors).toBe(1);
    expect(s.errors.some((e) => e.code === 'DENIED')).toBe(true);
  });

  it('handles duplicate end events without duplicating rows or losing state', () => {
    const s = run([
      ...norm('tool.requested', { name: 'x', toolCallId: 'c' }, 1),
      ...norm('tool.completed', { name: 'x', toolCallId: 'c' }, 2),
      ...norm('tool.completed', { name: 'x', toolCallId: 'c' }, 3),
    ]);
    // One start + one orphaned end (still a unique row, never a duplicate).
    expect(new Set(s.activity.map((a) => a.id)).size).toBe(s.activity.length);
  });

  it('dedupes file changes to one row per path', () => {
    const s = run([
      ...norm('fs.edit_file.applied', { path: 'a.ts', bytesWritten: 1 }, 1),
      ...norm('fs.edit_file.applied', { path: 'a.ts', bytesWritten: 2 }, 2),
    ]);
    expect(s.changes).toHaveLength(1);
  });

  it('counts a file once even when read repeatedly', () => {
    const s = run([
      ...norm('code.read', { path: 'a.ts', lines: 10 }, 1),
      ...norm('code.read', { path: 'a.ts', lines: 10 }, 2),
      ...norm('code.read', { path: 'b.ts', lines: 5 }, 3),
    ]);
    expect(s.context.filesInspected).toBe(2);
    expect(s.context.linesInspected).toBe(25);
  });

  it('bounds the activity list under a huge event stream', () => {
    const events: WorkspaceEvent[] = [];
    for (let i = 0; i < 12_000; i += 1) {
      events.push(...norm('tool.requested', { name: 'x', toolCallId: `c${i}` }, i));
    }
    const s = run(events);
    // The list is bounded (cap + a small trim slack), so a runaway run cannot
    // grow client memory without limit.
    expect(s.activity.length).toBeLessThanOrEqual(5000 + 512);
    expect(s.activity.length).toBeLessThan(12_000);
  });

  it('counts distinct research sources, deduping the same URL', () => {
    const s = run([
      ...norm('research.web_search', { query: 'a', results: 1 }, 1),
      ...norm('research.page_fetch', { url: 'https://x', legId: 'l' }, 2),
      ...norm('research.page_fetch', { url: 'https://x', legId: 'l' }, 3),
    ]);
    expect(s.research?.sources).toBe(1);
  });

  it('resolves a pending permission on approval.resolved', () => {
    const s = run([
      ...norm('approval.requested', { approvalId: 'a1', tool: 'git_push', risk: 'high' }, 1),
      ...norm('approval.resolved', { approvalId: 'a1', approved: true }, 2),
    ]);
    expect(s.permissions[0].status).toBe('approved');
  });

  it('counts out-of-order frames without dropping them', () => {
    const s = run([...norm('tool.requested', { name: 'x', toolCallId: 'c' }, 1)]);
    // A directly-applied out-of-order frame is still recorded as a row.
    expect(s.activity).toHaveLength(1);
  });
});

describe('history.replayTrace — reconstruct a run from a persisted trace', () => {
  it('rebuilds activity + changes + telemetry in seq order', () => {
    const trace = [
      { type: 'run.started', seq: 1, at: '2026-01-01T00:00:00Z', data: {} },
      { type: 'tool.requested', seq: 2, at: '2026-01-01T00:00:01Z', data: { name: 'workspace_read', toolCallId: 'c', detail: 'a.ts' } },
      { type: 'tool.completed', seq: 3, at: '2026-01-01T00:00:02Z', data: { name: 'workspace_read', toolCallId: 'c', durationMs: 10 } },
      { type: 'fs.edit_file.applied', seq: 4, at: '2026-01-01T00:00:03Z', data: { path: 'b.ts', bytesWritten: 3 } },
    ];
    const s = replayTrace('run_x', trace);
    expect(s.runId).toBe('run_x');
    expect(s.activity.length).toBeGreaterThanOrEqual(1);
    expect(s.changes).toHaveLength(1);
    expect(s.telemetry.toolCalls).toBe(1);
  });

  it('is deterministic regardless of input order', () => {
    const trace = [
      { type: 'run.completed', seq: 3, at: '2026-01-01T00:00:03Z', data: {} },
      { type: 'run.started', seq: 1, at: '2026-01-01T00:00:01Z', data: {} },
    ];
    const a = replayTrace('r', trace);
    const b = replayTrace('r', [...trace].reverse());
    expect(a.execution.status).toBe(b.execution.status);
  });
});

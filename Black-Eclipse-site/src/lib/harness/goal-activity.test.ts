import { describe, expect, it } from 'vitest';

import { goalActivitiesFromToolRows } from './goal-activity';

describe('goalActivitiesFromToolRows', () => {
  it('maps finished, failed and in-flight tool rows to the activity feed shape', () => {
    const items = goalActivitiesFromToolRows([
      { toolCallId: 'call_1', name: 'get_historical_prices', ok: true, durationMs: 812 },
      { toolCallId: 'call_2', name: 'analysis_run', ok: false },
      { toolCallId: 'call_3', name: 'analysis_run', ok: null },
    ]);

    expect(items.map((item) => item.status)).toEqual(['completed', 'failed', 'running']);
    expect(items[0].durationMs).toBe(812);
    expect(items[1].code).toBe('TOOL_ERROR');
    // The label is the SAME one the live chat uses for that tool, so a goal step
    // and a chat step never read differently for the same operation.
    expect(items[0].label).toBe(items[0].label.trim());
    expect(items[0].kind).toBe('tool');
  });

  it('keeps a retried step as two distinct rows', () => {
    const items = goalActivitiesFromToolRows([
      { name: 'analysis_run', ok: true },
      { name: 'analysis_run', ok: true },
    ]);
    expect(items).toHaveLength(2);
    expect(new Set(items.map((item) => item.id)).size).toBe(2);
  });

  it('skips nameless rows and empty input', () => {
    expect(goalActivitiesFromToolRows([])).toEqual([]);
    expect(goalActivitiesFromToolRows(null)).toEqual([]);
    expect(goalActivitiesFromToolRows([{ name: '   ', ok: true }])).toEqual([]);
  });
});

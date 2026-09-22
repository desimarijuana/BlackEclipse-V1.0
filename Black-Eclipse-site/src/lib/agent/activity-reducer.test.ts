import { describe, expect, it } from 'vitest';
import {
  endActivity,
  hasUniqueIds,
  initialActivityState,
  startActivity,
} from './activity-reducer';
import type { ActivityItem } from './response-model';

function item(id: string, name: string): ActivityItem {
  return { id, kind: 'retrieval', name, label: name, status: 'running' };
}

describe('activity reducer', () => {
  it('correlates a start and end and marks the row completed', () => {
    const s = initialActivityState();
    startActivity(s, item('retrieval:LIVE_STRUCTURED:macro_series', 'LIVE_STRUCTURED'));
    endActivity(s, {
      id: 'retrieval:LIVE_STRUCTURED:macro_series',
      name: 'LIVE_STRUCTURED',
      status: 'completed',
      summary: '3 records',
    });
    expect(s.activities).toHaveLength(1);
    expect(s.activities[0].status).toBe('completed');
    expect(s.activities[0].summary).toBe('3 records');
  });

  it('keeps ids unique when the same source runs twice (the duplicate-key bug)', () => {
    const s = initialActivityState();
    const logical = 'retrieval:LIVE_STRUCTURED:macro_series';
    startActivity(s, item(logical, 'LIVE_STRUCTURED'));
    endActivity(s, { id: logical, name: 'LIVE_STRUCTURED', status: 'completed' });
    startActivity(s, item(logical, 'LIVE_STRUCTURED'));
    endActivity(s, { id: logical, name: 'LIVE_STRUCTURED', status: 'failed', code: 'TOOL_ERROR' });

    expect(s.activities).toHaveLength(2);
    expect(hasUniqueIds(s.activities)).toBe(true);
    expect(s.activities[0].status).toBe('completed');
    expect(s.activities[1].status).toBe('failed');
  });

  it('correlates overlapping runs of the same operation LIFO', () => {
    const s = initialActivityState();
    const logical = 'tool:market_get_quote';
    startActivity(s, { id: logical, kind: 'tool', name: 'market_get_quote', label: 'quote', status: 'running' });
    startActivity(s, { id: logical, kind: 'tool', name: 'market_get_quote', label: 'quote', status: 'running' });
    // The first end closes the most recent (second) instance.
    endActivity(s, { id: logical, name: 'market_get_quote', status: 'completed', durationMs: 10 });
    expect(s.activities[1].status).toBe('completed');
    expect(s.activities[0].status).toBe('running');
    endActivity(s, { id: logical, name: 'market_get_quote', status: 'failed' });
    expect(s.activities[0].status).toBe('failed');
    expect(hasUniqueIds(s.activities)).toBe(true);
  });

  it('falls back to the most recent running item when no id is provided', () => {
    const s = initialActivityState();
    startActivity(s, item('a', 'yfinance'));
    endActivity(s, { name: 'yfinance', status: 'completed' });
    expect(s.activities[0].status).toBe('completed');
  });

  it('records an orphan end with a unique id rather than dropping it', () => {
    const s = initialActivityState();
    endActivity(s, { name: 'mystery', status: 'failed', code: 'TOOL_ERROR' });
    expect(s.activities).toHaveLength(1);
    expect(s.activities[0].status).toBe('failed');
    expect(hasUniqueIds(s.activities)).toBe(true);
  });
});

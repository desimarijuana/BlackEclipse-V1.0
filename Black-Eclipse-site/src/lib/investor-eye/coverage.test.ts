import { describe, it, expect } from 'vitest';
import { conflictCoverage } from './coverage';
import type { InvestorEyeState, NormalizedEvent, SourceStatus } from './types';

function event(over: Partial<NormalizedEvent>): NormalizedEvent {
  return {
    dedupKey: Math.random().toString(36),
    title: 't',
    eventType: 'conflict',
    severity: 'high',
    channels: [], commodities: [], sectors: [], securities: [], countries: [],
    confidence: 0.5, sourceCount: 1, sources: [], primarySource: 'gdelt',
    publishedAt: '2026-09-16T00:00:00Z',
    ...over,
  };
}

function src(id: string, state: SourceStatus['state']): SourceStatus {
  return { id, name: id, capabilities: ['EVENTS'], requiresCredentials: false, state };
}

function state(events: NormalizedEvent[], sources: SourceStatus[], eventsUnavailable = false): Pick<InvestorEyeState, 'events' | 'status' | 'eventsUnavailable'> {
  return { events, status: { provenance: 'LIVE', updatedAt: null, label: '', sources }, eventsUnavailable };
}

describe('conflictCoverage', () => {
  it('reports observed when conflict events exist', () => {
    const r = conflictCoverage(state([event({ eventType: 'conflict' })], [src('gdelt', 'available')]));
    expect(r.status).toBe('observed');
    expect(r.conflictCount).toBe(1);
  });

  it('reports an honest quiet zero when every source is healthy', () => {
    const r = conflictCoverage(state([event({ eventType: 'trade' })], [src('gdelt', 'available'), src('usgs', 'available')]));
    expect(r.status).toBe('quiet');
    expect(r.explanation).toMatch(/2 healthy sources/);
  });

  it('reports degraded when sources failed, so the gap is not read as calm', () => {
    const r = conflictCoverage(state([], [src('gdelt', 'error'), src('usgs', 'available')]));
    expect(r.status).toBe('degraded');
    expect(r.degradedSourceIds).toEqual(['gdelt']);
    expect(r.explanation).toMatch(/coverage gap/);
  });

  it('treats a throttle as degraded, not quiet', () => {
    const r = conflictCoverage(state([], [src('gdelt', 'rate_limited')]));
    expect(r.status).toBe('degraded');
  });

  it('reports unavailable when the event feed itself failed', () => {
    const r = conflictCoverage(state([], [src('gdelt', 'error')], true));
    expect(r.status).toBe('unavailable');
  });

  it('counts retained (replayed) events', () => {
    const r = conflictCoverage(state([event({ eventType: 'conflict', replayed: true })], [src('gdelt', 'available')]));
    expect(r.replayedCount).toBe(1);
    expect(r.status).toBe('observed');
  });

  it('handles a null state without throwing', () => {
    expect(conflictCoverage(null).status).toBe('unavailable');
  });
});

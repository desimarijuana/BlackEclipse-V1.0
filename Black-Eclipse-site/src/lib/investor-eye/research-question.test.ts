import { describe, it, expect } from 'vitest';
import { eventResearchQuestion, windowConflictQuestion } from './research-question';
import type { NormalizedEvent } from './types';

function event(over: Partial<NormalizedEvent> = {}): NormalizedEvent {
  return {
    dedupKey: 'x',
    title: 'Explosion near the Strait of Hormuz',
    eventType: 'conflict',
    severity: 'high',
    channels: [], commodities: [], sectors: [], securities: [],
    countries: ['IR', 'AE'],
    placeName: 'Strait of Hormuz',
    actors: [{ name: 'IRGC' }],
    confidence: 0.6, sourceCount: 2, sources: [], primarySource: 'gdelt',
    publishedAt: '2026-09-16T07:30:00Z',
    ...over,
  };
}

describe('eventResearchQuestion', () => {
  it('names the event, place and date and asks for corroboration', () => {
    const q = eventResearchQuestion(event());
    expect(q).toContain('Explosion near the Strait of Hormuz');
    expect(q).toContain('Strait of Hormuz');
    expect(q).toContain('2026-09-16');
    expect(q).toMatch(/corroborate/i);
    expect(q).toMatch(/contradictory/i);
  });

  it('includes reported actors and asks for citations and unknowns', () => {
    const q = eventResearchQuestion(event());
    expect(q).toContain('IRGC');
    expect(q).toMatch(/cite each finding/i);
    expect(q).toMatch(/remains unknown/i);
  });

  it('falls back to countries when no place is known, without inventing one', () => {
    const q = eventResearchQuestion(event({ placeName: undefined }));
    expect(q).toContain('IR, AE');
  });

  it('handles an event with no actors', () => {
    const q = eventResearchQuestion(event({ actors: [] }));
    expect(q).not.toContain('Reported actors');
    expect(q).toContain('corroborate');
  });
});

describe('windowConflictQuestion', () => {
  it('names the window and asks for cited, confirmed-vs-unconfirmed reporting', () => {
    const q = windowConflictQuestion(168);
    expect(q).toContain('last 7 days');
    expect(q).toMatch(/cite independent sources/i);
    expect(q).toMatch(/confirmed events from single-source/i);
  });

  it('uses hours for a sub-day window and days otherwise', () => {
    expect(windowConflictQuestion(12)).toContain('last 12 hours');
    expect(windowConflictQuestion(24)).toContain('last 1 day');
  });

  it('forbids invented events and allows an honest quiet result', () => {
    const q = windowConflictQuestion(48);
    expect(q).toMatch(/do not invent events/i);
    expect(q).toMatch(/genuinely quiet/i);
  });
});

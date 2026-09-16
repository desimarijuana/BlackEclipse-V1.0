import { describe, it, expect } from 'vitest';
import { formatEventRecord, explainPromptFor, EXPLAIN_SYSTEM_PROMPT } from './event-record';
import { rowToEvent } from './state';

// The explain route renders an event into the analyst's prompt. These tests pin
// the SHAPE of that record: if actors, provenance or the location-precision line
// silently disappear, the analyst starts guessing. Pure, so no route needed.

const row = {
  id: 'r1', dedupKey: 'k1', title: 'ACTOR / ACTOR — Somewhere', summary: 'A summary',
  headline: 'A real headline', description: 'A real description',
  actors: JSON.stringify([{ name: 'IRAN', typeCode: 'GOV', countryCode: 'IRN' }]),
  providerCodes: JSON.stringify({ cameoRoot: '19', goldstein: -10 }),
  placeName: 'Tehran', geoMethod: 'capital',
  eventType: 'conflict', severity: 'high',
  channels: JSON.stringify(['Energy']), commodities: JSON.stringify(['Crude Oil']),
  sectors: JSON.stringify(['Energy']), securities: JSON.stringify([]),
  countries: JSON.stringify(['IR']),
  lon: 51.39, lat: 35.69, confidence: 0.8, relevance: 0.7,
  relevanceReasons: JSON.stringify(['material conflict']),
  sourceCount: 2,
  sources: JSON.stringify([{ id: 'a', name: 'Example News', url: 'https://a.example/story' }]),
  primarySource: 'gdelt',
  publishedAt: new Date('2026-09-16T10:00:00Z'),
  firstSeen: new Date('2026-09-16T10:05:00Z'),
  lastUpdated: new Date('2026-09-16T10:10:00Z'),
  status: 'active',
};

describe('formatEventRecord', () => {
  it('includes the fields the analyst needs, with geo precision stated', () => {
    const record = formatEventRecord(rowToEvent(row));
    expect(record).toContain('A real headline');
    expect(record).toContain('conflict');
    expect(record).toContain('Tehran');
    expect(record).toContain('country capital (policy event)');
    expect(record).toContain('IRAN');
    expect(record).toContain('Government');
    expect(record).toContain('CAMEO root: 19');
    expect(record).toContain('Goldstein: -10');
    expect(record).toContain('Example News');
    expect(record).toContain('A real description');
  });

  it('marks text-derived exposure as derived, so inference is separable', () => {
    const record = formatEventRecord(rowToEvent(row));
    expect(record).toContain('Economic channels (derived from text)');
    expect(record).toContain('Commodities (derived)');
  });

  it('calls confidence data quality, not certainty', () => {
    expect(formatEventRecord(rowToEvent(row))).toContain('NOT certainty');
  });

  it('omits absent optional fields rather than printing placeholders', () => {
    const bare = rowToEvent({
      ...row,
      headline: null, description: null, actors: '[]', providerCodes: '{}',
      placeName: null, geoMethod: null, relevance: undefined, relevanceReasons: '[]',
      sources: '[]', channels: '[]', commodities: '[]', sectors: '[]',
    } as never);
    const record = formatEventRecord(bare);
    expect(record).not.toContain('Location precision');
    expect(record).not.toContain('Actors:');
    expect(record).not.toContain('CAMEO root');
    expect(record).toContain('Sources: none captured');
    // Falls back to the raw title when there is no headline.
    expect(record).toContain('ACTOR / ACTOR');
  });
});

describe('explainPromptFor / system prompt', () => {
  it('embeds the record in the user prompt', () => {
    const prompt = explainPromptFor(rowToEvent(row));
    expect(prompt).toContain('EVENT RECORD');
    expect(prompt).toContain('A real headline');
  });

  it('states the honesty rules that keep the answer grounded', () => {
    expect(EXPLAIN_SYSTEM_PROMPT).toMatch(/never invent/i);
    expect(EXPLAIN_SYSTEM_PROMPT).toMatch(/potential/i);
    expect(EXPLAIN_SYSTEM_PROMPT).toMatch(/provenance/i);
  });
});

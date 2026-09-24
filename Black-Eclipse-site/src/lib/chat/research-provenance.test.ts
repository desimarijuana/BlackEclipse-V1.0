import { describe, expect, it } from 'vitest';
import {
  coerceResearchRun,
  coverageCounts,
  hasSecondarySource,
  mergeLimitations,
  shortDate,
  sourceIndexById,
  sourceMarkers,
  summarizeRun,
} from './research-provenance';
import type { ResearchCitation, ResearchRunInfo } from '@/lib/harness/types';

const citation = (over: Partial<ResearchCitation> = {}): ResearchCitation => ({
  evidenceId: 'e1',
  kind: 'filing',
  ...over,
});

describe('coerceResearchRun', () => {
  it('accepts a run-info object and rejects everything else', () => {
    expect(coerceResearchRun({ status: 'partial' })).toMatchObject({ status: 'partial' });
    expect(coerceResearchRun(null)).toBeNull();
    expect(coerceResearchRun(undefined)).toBeNull();
    expect(coerceResearchRun('partial')).toBeNull();
    expect(coerceResearchRun({})).toBeNull();
    expect(coerceResearchRun({ metadata: {} })).toBeNull();
  });
});

describe('shortDate', () => {
  it('extracts a YYYY-MM-DD day and rejects non-dates', () => {
    expect(shortDate('2026-02-25T00:00:00Z')).toBe('2026-02-25');
    expect(shortDate('2026-02-25')).toBe('2026-02-25');
    expect(shortDate('unknown')).toBeNull();
    expect(shortDate('')).toBeNull();
    expect(shortDate(null)).toBeNull();
    expect(shortDate(undefined)).toBeNull();
  });
});

describe('source numbering + markers', () => {
  it('numbers sources 1-based and keeps first occurrence', () => {
    const index = sourceIndexById([
      citation({ evidenceId: 'a' }),
      citation({ evidenceId: 'b' }),
      citation({ evidenceId: 'a' }),
    ]);
    expect(index.get('a')).toBe(1);
    expect(index.get('b')).toBe(2);
  });

  it('maps evidence ids to numbers and drops unknown ids', () => {
    const index = sourceIndexById([citation({ evidenceId: 'a' }), citation({ evidenceId: 'b' })]);
    expect(sourceMarkers(['b', 'a'], index)).toEqual([2, 1]);
    expect(sourceMarkers(['a', 'missing', 'b'], index)).toEqual([1, 2]);
    expect(sourceMarkers(['missing'], index)).toEqual([]);
  });
});

describe('mergeLimitations', () => {
  it('merges limitations + missing evidence, de-duplicated, order preserved', () => {
    const merged = mergeLimitations({
      taskType: 'financial_comparison',
      status: 'partial',
      citations: [],
      assumptions: [],
      estimates: [],
      interpretations: [],
      limitations: ['basis unconfirmed', 'period missing'],
      missingEvidence: ['period missing', 'net income absent'],
      conflicts: [],
      calculations: [],
    });
    expect(merged).toEqual(['basis unconfirmed', 'period missing', 'net income absent']);
  });

  it('is empty for a null/absent metadata object', () => {
    expect(mergeLimitations(null)).toEqual([]);
    expect(mergeLimitations(undefined)).toEqual([]);
  });
});

describe('coverageCounts', () => {
  it('counts covered vs unmet and excludes not_applicable', () => {
    const { covered, unmet, total } = coverageCounts([
      { legId: '1', metric: 'revenue', status: 'covered', evidenceIds: [] },
      { legId: '2', metric: 'netIncome', status: 'unavailable', evidenceIds: [] },
      { legId: '3', metric: 'eps', status: 'not_applicable', evidenceIds: [] },
    ]);
    expect(covered).toBe(1);
    expect(unmet).toBe(1);
    expect(total).toBe(3);
  });
});

describe('hasSecondarySource', () => {
  it('detects a secondary tier and ignores primary/structured', () => {
    expect(hasSecondarySource([citation({ sourceType: 'primary' })])).toBe(false);
    expect(hasSecondarySource([citation({ sourceType: 'structured' })])).toBe(false);
    expect(hasSecondarySource([citation({ sourceType: 'secondary' })])).toBe(true);
  });
});

describe('summarizeRun', () => {
  it('assembles a compact summary from legs + citations', () => {
    const info: ResearchRunInfo = {
      status: 'partial',
      coverage: {
        status: 'partial',
        legs: [
          { legId: '1', metric: 'revenue', status: 'covered', evidenceIds: ['a'] },
          { legId: '2', metric: 'netIncome', status: 'unavailable', evidenceIds: [] },
        ],
      },
      metadata: {
        taskType: 'financial_comparison',
        status: 'partial',
        citations: [citation({ evidenceId: 'a' })],
        assumptions: [],
        estimates: [],
        interpretations: [],
        limitations: [],
        missingEvidence: [],
        conflicts: [],
        calculations: [],
      },
    };
    expect(summarizeRun(info)).toBe('1/2 legs covered · 1 unmet · 1 source(s)');
  });

  it('omits counts that do not apply', () => {
    expect(summarizeRun({ status: 'rejected' })).toBe('');
  });
});

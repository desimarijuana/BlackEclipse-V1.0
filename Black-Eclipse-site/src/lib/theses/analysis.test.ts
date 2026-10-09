import { describe, it, expect } from 'vitest';
import {
  assessAssumptionImpacts,
  summarizeThesis,
  isStance,
  overlapCount,
  tokens,
} from './analysis';
import type { ThesisEvidenceRecord } from './types';

const ev = (stance: 'supporting' | 'contradicting', summary: string): ThesisEvidenceRecord => ({
  id: Math.random().toString(36).slice(2),
  stance,
  summary,
  sourceUrl: null,
  sourceType: 'user',
  publishedAt: null,
  retrievedAt: new Date().toISOString(),
});

describe('tokens', () => {
  it('drops short words and stopwords', () => {
    expect(tokens('The revenue is growing rapidly')).toEqual(['revenue', 'growing', 'rapidly']);
  });
});

describe('overlapCount', () => {
  it('counts shared significant tokens only', () => {
    expect(overlapCount('revenue growth', 'strong revenue growth in the quarter')).toBe(2);
    expect(overlapCount('revenue growth', 'unrelated news about weather')).toBe(0);
  });
});

describe('assessAssumptionImpacts', () => {
  it('marks an assumption unmentioned without matching evidence', () => {
    const [im] = assessAssumptionImpacts(['margin expansion'], [ev('supporting', 'weather was mild')]);
    expect(im.verdict).toBe('unmentioned');
  });

  it('marks supported when only supporting evidence matches', () => {
    const [im] = assessAssumptionImpacts(['free cash flow growth'], [ev('supporting', 'free cash flow growth accelerated')]);
    expect(im.verdict).toBe('supported');
  });

  it('marks contradicted when contradiction outweighs support', () => {
    const [im] = assessAssumptionImpacts(
      ['debt reduction'],
      [ev('supporting', 'debt reduction began'), ev('contradicting', 'debt reduction reversed'), ev('contradicting', 'debt reduction stalled')],
    );
    expect(im.verdict).toBe('contradicted');
    expect(im.contradicting).toBe(2);
    expect(im.supporting).toBe(1);
  });

  it('marks weakened when there is both, contradicting not dominant', () => {
    const [im] = assessAssumptionImpacts(['dividend growth'], [ev('supporting', 'dividend growth held'), ev('contradicting', 'dividend growth risk')]);
    expect(im.verdict).toBe('weakened');
  });
});

describe('summarizeThesis', () => {
  it('reports no-evidence coverage with no evidence', () => {
    const h = summarizeThesis({ evidence: [] });
    expect(h.coverage).toBe('no-evidence');
    expect(h.suggestedStatus).toBe('active');
  });

  it('suggests broken when contradictions dominate more than 2:1', () => {
    const h = summarizeThesis({ evidence: [ev('contradicting', 'a'), ev('contradicting', 'b'), ev('contradicting', 'c'), ev('supporting', 'd')] });
    expect(h.suggestedStatus).toBe('broken');
    expect(h.netScore).toBe(-2);
  });

  it('suggests weakening on a marginal negative', () => {
    const h = summarizeThesis({ evidence: [ev('supporting', 'a'), ev('contradicting', 'b'), ev('contradicting', 'c')] });
    expect(h.suggestedStatus).toBe('weakening');
  });

  it('reports well-supported on a positive net', () => {
    const h = summarizeThesis({ evidence: [ev('supporting', 'a'), ev('supporting', 'b')] });
    expect(h.coverage).toBe('well-supported');
    expect(h.suggestedStatus).toBe('active');
  });
});

describe('isStance', () => {
  it('accepts only the two stances', () => {
    expect(isStance('supporting')).toBe(true);
    expect(isStance('contradicting')).toBe(true);
    expect(isStance('maybe')).toBe(false);
  });
});

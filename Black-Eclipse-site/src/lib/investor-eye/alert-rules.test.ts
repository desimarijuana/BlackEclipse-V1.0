import { describe, it, expect } from 'vitest';
import {
  defaultRule, matchRule, evaluateRules, distanceKm, parseRule,
  RULE_PRESETS, MAX_RULES,
} from './alert-rules';
import type { EventAlertRule } from './alert-rules';
import type { NormalizedEvent } from './types';

function event(overrides: Partial<NormalizedEvent> = {}): NormalizedEvent {
  return {
    id: 'e1',
    dedupKey: 'e1',
    title: 'Shelling near the port',
    eventType: 'conflict',
    severity: 'critical',
    channels: [],
    commodities: ['Crude Oil'],
    sectors: [],
    securities: [],
    countries: ['TR'],
    lon: 30,
    lat: 39,
    confidence: 0.8,
    sourceCount: 1,
    sources: [],
    primarySource: 'gdelt',
    publishedAt: '2026-09-16T10:00:00.000Z',
    relevance: 0.7,
    ...overrides,
  };
}

describe('distanceKm', () => {
  it('is zero for identical points', () => {
    expect(distanceKm(10, 20, 10, 20)).toBe(0);
  });
  it('matches a known great-circle distance within tolerance', () => {
    // London → Paris ≈ 344 km.
    expect(distanceKm(51.51, -0.13, 48.86, 2.35)).toBeGreaterThan(330);
    expect(distanceKm(51.51, -0.13, 48.86, 2.35)).toBeLessThan(360);
  });
});

describe('matchRule', () => {
  it('matches on event type and severity and reports reasons', () => {
    const rule = defaultRule({ name: 'conflict', eventTypes: ['conflict'], minSeverity: 'high' });
    const m = matchRule(event(), rule);
    expect(m).not.toBeNull();
    expect(m!.reasons.join(' ')).toContain('conflict');
    expect(m!.reasons.join(' ')).toContain('severity');
  });

  it('rejects an event below the severity floor', () => {
    const rule = defaultRule({ name: 'crit', minSeverity: 'critical' });
    expect(matchRule(event({ severity: 'medium' }), rule)).toBeNull();
  });

  it('rejects a different event type', () => {
    const rule = defaultRule({ name: 'energy', eventTypes: ['energy'] });
    expect(matchRule(event({ eventType: 'conflict' }), rule)).toBeNull();
  });

  it('matches countries case-insensitively via the caller', () => {
    const rule = defaultRule({ name: 'tr', countries: ['TR'] });
    expect(matchRule(event(), rule)).not.toBeNull();
    const miss = defaultRule({ name: 'us', countries: ['US'] });
    expect(matchRule(event(), miss)).toBeNull();
  });

  it('matches commodities as substrings', () => {
    const rule = defaultRule({ name: 'oil', commodities: ['crude'] });
    expect(matchRule(event(), rule)).not.toBeNull();
  });

  it('matches keywords against title and summary', () => {
    const rule = defaultRule({ name: 'kw', keywords: ['port'] });
    expect(matchRule(event(), rule)).not.toBeNull();
    expect(matchRule(event({ title: 'Unrelated', summary: undefined }), rule)).toBeNull();
  });

  it('enforces the geographic fence and reports the distance', () => {
    // ~111 km north of the event.
    const rule = defaultRule({ name: 'near', near: { lat: 40, lon: 30, radiusKm: 200 } });
    const m = matchRule(event(), rule);
    expect(m).not.toBeNull();
    expect(m!.distanceKm).toBeGreaterThan(100);
    expect(m!.distanceKm).toBeLessThan(130);

    const tooFar = defaultRule({ name: 'far', near: { lat: 45, lon: 30, radiusKm: 50 } });
    expect(matchRule(event(), tooFar)).toBeNull();
  });

  it('never matches an event without coordinates when a fence is set', () => {
    const rule = defaultRule({ name: 'near', near: { lat: 39, lon: 30, radiusKm: 10 } });
    expect(matchRule(event({ lon: undefined, lat: undefined }), rule)).toBeNull();
  });

  it('refuses to match a rule with no predicates (would fire on everything)', () => {
    const empty = defaultRule({ name: 'empty', minSeverity: 'low' });
    expect(matchRule(event(), empty)).toBeNull();
  });

  it('respects the enabled flag', () => {
    const rule = defaultRule({ name: 'off', enabled: false, eventTypes: ['conflict'], minSeverity: 'high' });
    expect(matchRule(event(), rule)).toBeNull();
  });

  it('applies relevance and confidence floors', () => {
    const rel = defaultRule({ name: 'rel', minRelevance: 0.8 });
    expect(matchRule(event(), rel)).toBeNull();
    const conf = defaultRule({ name: 'conf', minConfidence: 0.9 });
    expect(matchRule(event(), conf)).toBeNull();
  });
});

describe('evaluateRules', () => {
  it('collects matches and the triggered rule ids', () => {
    const rules = [
      defaultRule({ id: 'a', name: 'A', eventTypes: ['conflict'], minSeverity: 'high' }),
      defaultRule({ id: 'b', name: 'B', eventTypes: ['energy'], minSeverity: 'high' }),
    ];
    const out = evaluateRules([event()], rules);
    expect(out.matches).toHaveLength(1);
    expect(out.triggeredRuleIds).toEqual(['a']);
  });

  it('skips disabled rules and reports UNAVAILABLE for an empty window', () => {
    const rules = [defaultRule({ name: 'A', enabled: false, eventTypes: ['conflict'], minSeverity: 'high' })];
    const out = evaluateRules([], rules);
    expect(out.matches).toHaveLength(0);
    expect(out.provenance).toBe('UNAVAILABLE');
  });
});

describe('parseRule', () => {
  it('accepts a valid draft and clamps unit fields', () => {
    const r = parseRule({ name: 'My rule', minConfidence: 5, minRelevance: -2, countries: ['tr'] });
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.rule.minConfidence).toBe(1);
      expect(r.rule.minRelevance).toBe(0);
      expect(r.rule.countries).toEqual(['TR']);
    }
  });

  it('requires a name', () => {
    expect(parseRule({ name: '   ' }).ok).toBe(false);
    expect(parseRule({}).ok).toBe(false);
  });

  it('validates the geographic fence', () => {
    expect(parseRule({ name: 'x', near: { lat: 999, lon: 0, radiusKm: 10 } }).ok).toBe(false);
    const ok = parseRule({ name: 'x', near: { lat: 10, lon: 20, radiusKm: 50 } });
    expect(ok.ok).toBe(true);
    if (ok.ok) expect(ok.rule.near).toEqual({ lat: 10, lon: 20, radiusKm: 50 });
  });

  it('rejects non-object input', () => {
    expect(parseRule(null).ok).toBe(false);
    expect(parseRule('nope').ok).toBe(false);
  });
});

describe('presets', () => {
  it('every preset produces a rule that can match something', () => {
    for (const p of RULE_PRESETS) {
      const parsed = parseRule({ ...p.rule, id: `preset-${p.id}` });
      expect(parsed.ok, p.id).toBe(true);
      if (parsed.ok) {
        // Not an empty (unmatchable) rule.
        const probe: EventAlertRule = parsed.rule;
        const relevant =
          probe.eventTypes.length > 0 || probe.minSeverity !== 'low' ||
          probe.minRelevance > 0 || probe.commodities.length > 0 ||
          probe.keywords.length > 0 || probe.countries.length > 0 || Boolean(probe.near);
        expect(relevant, p.id).toBe(true);
      }
    }
  });

  it('the conflict preset fires on a critical conflict', () => {
    const preset = RULE_PRESETS.find((p) => p.id === 'conflict-critical')!;
    const parsed = parseRule({ ...preset.rule });
    expect(parsed.ok).toBe(true);
    if (parsed.ok) expect(matchRule(event(), parsed.rule)).not.toBeNull();
  });

  it('MAX_RULES is a sane bound', () => {
    expect(MAX_RULES).toBeGreaterThan(0);
    expect(MAX_RULES).toBeLessThanOrEqual(200);
  });
});

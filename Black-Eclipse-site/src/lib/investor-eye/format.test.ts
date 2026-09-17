import { describe, it, expect } from 'vitest';
import {
  formatClock, formatUtc, formatDateTime, formatAxisTime, timeInZone,
  zoneAbbrev, relativeAge, formatPct, formatEventTitle, DEFAULT_TIMEZONE,
} from './format';

const ISO = '2026-09-16T21:30:00.000Z';

describe('timezone-aware clocks', () => {
  it('formats in an explicit zone and ALWAYS prints the zone', () => {
    // A bare clock would be ambiguous, so the zone is part of the contract.
    expect(formatClock(ISO, 'UTC')).toMatch(/21:30 UTC/);
    const ny = formatClock(ISO, 'America/New_York');
    expect(ny).toMatch(/^17:30 /);
    expect(ny).toContain('EDT');
  });

  it('shifts the calendar day when the zone crosses midnight', () => {
    // 21:30 UTC is the NEXT day in Tokyo.
    expect(timeInZone(ISO, 'Asia/Tokyo')).toBe('06:30');
    expect(timeInZone(ISO, 'America/Los_Angeles')).toBe('14:30');
  });

  it('falls back to UTC for an invalid zone rather than throwing', () => {
    expect(formatClock(ISO, 'Not/AZone')).toMatch(/21:30 UTC/);
    expect(timeInZone(ISO, 'Not/AZone')).toBe('21:30');
  });

  it('labels the zone abbreviation, defaulting to UTC', () => {
    expect(zoneAbbrev(ISO, 'UTC')).toBe('UTC');
    expect(zoneAbbrev(ISO)).toBe('UTC');
    expect(zoneAbbrev(null, 'UTC')).toBe('UTC');
  });

  it('returns a placeholder for missing/invalid input', () => {
    expect(formatClock(null)).toBe('—');
    expect(formatClock('nope')).toBe('—');
    expect(formatDateTime(undefined)).toBe('—');
    expect(timeInZone(null)).toBe('');
  });

  it('formatDateTime carries the date and the zone', () => {
    const s = formatDateTime(ISO, 'UTC');
    expect(s).toContain('16 Sep');
    expect(s).toContain('21:30');
    expect(s).toContain('UTC');
  });

  it('formatAxisTime is sortable YYYY-MM-DD HH:MM', () => {
    expect(formatAxisTime(ISO, 'UTC')).toBe('2026-09-16 21:30');
  });

  // Regression: callers used `formatUtc(x).slice(11, 16)` expecting an ISO
  // string, but formatUtc returns a 9-character display string — the slice was
  // ALWAYS empty, so source/timeline/feed times rendered blank.
  it('formatUtc is a short display string, never an ISO string', () => {
    const s = formatUtc(ISO);
    expect(s).toBe('21:30 UTC');
    expect(s.length).toBe(9);
    expect(s.slice(11, 16)).toBe('');
    // Use formatClock for the clock, and this never comes up:
    expect(formatClock(ISO, 'UTC')).toContain('21:30');
  });

  it('exposes a documented default zone', () => {
    expect(DEFAULT_TIMEZONE).toBe('UTC');
  });
});

describe('relativeAge', () => {
  const now = Date.parse('2026-09-16T22:00:00.000Z');
  it('is deterministic against a supplied now', () => {
    expect(relativeAge('2026-09-16T21:56:00.000Z', now)).toBe('4m ago');
    expect(relativeAge('2026-09-16T20:00:00.000Z', now)).toBe('2h ago');
    expect(relativeAge('2026-09-14T22:00:00.000Z', now)).toBe('2d ago');
    expect(relativeAge('2026-09-16T21:59:40.000Z', now)).toBe('20s ago');
  });
  it('never reports a negative age', () => {
    expect(relativeAge('2026-09-16T23:00:00.000Z', now)).toBe('0s ago');
  });
  it('handles missing input', () => {
    expect(relativeAge(null, now)).toBe('—');
  });
});

describe('formatPct / formatEventTitle (unchanged contracts)', () => {
  it('formats percentages', () => {
    expect(formatPct(1.234)).toBe('+1.23%');
    expect(formatPct(-0.5)).toBe('-0.50%');
    expect(formatPct(undefined)).toBe('—');
  });
  it('restructures a synthesized provider title', () => {
    expect(formatEventTitle('IRANIAN / IRAN — Shandong, China')).toBe('IRANIAN and IRAN in Shandong, China');
    expect(formatEventTitle('POLICE — Washington, United States')).toBe('POLICE in Washington, United States');
  });
  it('leaves a real headline alone', () => {
    const h = 'Port workers strike over pay in Rotterdam';
    expect(formatEventTitle(h)).toBe(h);
  });
});

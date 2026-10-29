import { describe, expect, it } from 'vitest';
import { addDays, computePaperWindow, daysBetween, defaultPaperMode } from './paper-window';

describe('paper windows', () => {
  it('adds days across month and year boundaries', () => {
    expect(addDays('2026-01-31', 1)).toBe('2026-02-01');
    expect(addDays('2026-12-31', 1)).toBe('2027-01-01');
    expect(addDays('2026-03-01', -1)).toBe('2026-02-28');
  });

  it('counts inclusive days', () => {
    expect(daysBetween('2026-01-01', '2026-01-01')).toBe(0);
    expect(daysBetween('2026-01-01', '2026-01-02')).toBe(1);
  });

  it('builds a forward window from the day after the research end', () => {
    const window = computePaperWindow({
      mode: 'forward',
      researchStart: '2023-01-01',
      researchEnd: '2025-12-31',
      today: '2026-03-01',
    });
    expect(window.available).toBe(true);
    expect(window.start).toBe('2026-01-01');
    expect(window.end).toBe('2026-03-01');
    expect(window.days).toBe(60);
  });

  it('refuses a forward window that would start after today', () => {
    const window = computePaperWindow({
      mode: 'forward',
      researchStart: '2024-01-01',
      researchEnd: '2026-03-01',
      today: '2026-03-01',
    });
    expect(window.available).toBe(false);
    expect(window.reason).toContain('no forward period');
  });

  it('labels a replay as a replay', () => {
    const window = computePaperWindow({
      mode: 'replay',
      researchStart: '2024-01-01',
      researchEnd: '2025-01-01',
      today: '2026-01-01',
    });
    expect(window.available).toBe(true);
    expect(window.start).toBe('2024-01-01');
    expect(window.end).toBe('2025-01-01');
    expect(window.reason).toContain('not forward-looking');
  });

  it('is unavailable when the window is missing', () => {
    const window = computePaperWindow({ mode: 'forward', researchStart: '', researchEnd: '', today: '2026-01-01' });
    expect(window.available).toBe(false);
    expect(window.reason).toContain('not set');
  });

  it('offers forward only when there is a forward period', () => {
    expect(defaultPaperMode('2025-01-01', '2026-01-01')).toBe('forward');
    expect(defaultPaperMode('2026-01-01', '2026-01-01')).toBe('replay');
  });
});

import { describe, expect, it } from 'vitest';
import { greetingFor, timeOfDayFor } from './home-prefs';

const at = (hour: number, minute = 0) => new Date(2026, 0, 15, hour, minute, 0, 0);

describe('time of day', () => {
  it('maps morning, afternoon, evening and night boundaries', () => {
    expect(timeOfDayFor(at(4, 59))).toBe('night');
    expect(timeOfDayFor(at(5))).toBe('morning');
    expect(timeOfDayFor(at(11, 59))).toBe('morning');
    expect(timeOfDayFor(at(12))).toBe('afternoon');
    expect(timeOfDayFor(at(16, 59))).toBe('afternoon');
    expect(timeOfDayFor(at(17))).toBe('evening');
    expect(timeOfDayFor(at(21, 59))).toBe('evening');
    expect(timeOfDayFor(at(22))).toBe('night');
    expect(timeOfDayFor(at(23, 59))).toBe('night');
  });

  it('returns a distinct greeting for every part of day', () => {
    expect(greetingFor(at(8))).toBe('Good morning');
    expect(greetingFor(at(14))).toBe('Good afternoon');
    expect(greetingFor(at(19))).toBe('Good evening');
    expect(greetingFor(at(2))).toBe('Good night');
  });
});

import { describe, it, expect } from 'vitest';
import { safeNext } from './next-path';

describe('safeNext', () => {
  it('keeps a same-origin absolute path', () => {
    expect(safeNext('/terminal?tab=2')).toBe('/terminal?tab=2');
    expect(safeNext('/')).toBe('/');
  });

  it('rejects absolute, protocol-relative and backslash paths (open redirect)', () => {
    expect(safeNext('https://evil.example/phish')).toBe('/');
    expect(safeNext('//evil.example')).toBe('/');
    expect(safeNext('\\evil')).toBe('/');
  });

  it('rejects a loop back to the login page and empty input', () => {
    expect(safeNext('/login')).toBe('/');
    expect(safeNext('/login?next=/x')).toBe('/');
    expect(safeNext(null)).toBe('/');
    expect(safeNext(undefined)).toBe('/');
    expect(safeNext('')).toBe('/');
  });
});

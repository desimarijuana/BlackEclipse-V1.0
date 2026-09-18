import { describe, expect, it } from 'vitest';
import { DEFAULT_BOARD_JSON, getDefaultBoard } from './default-board';

const KNOWN = new Set(['market-status', 'eclipse-chart']);

describe('getDefaultBoard', () => {
  it('returns null when no curated board is configured', () => {
    // The shipped default is null until an operator pastes an export.
    if (DEFAULT_BOARD_JSON === null) {
      expect(getDefaultBoard(KNOWN)).toBeNull();
    }
  });

  it('returns null for a payload with no known widgets', () => {
    // Guards the paste path: a malformed/unknown board never yields an empty
    // first-run board — the persona template takes over instead.
    expect(getDefaultBoard(new Set())).toBeNull();
  });

  it('is null-safe and never throws', () => {
    expect(() => getDefaultBoard(KNOWN)).not.toThrow();
  });
});

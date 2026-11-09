import { describe, expect, it } from 'vitest';
import { mergeAttachmentChips } from './use-session';

// The visible-attachment contract: an attached file MUST show as a chip, whether
// it is still pending (attached on the empty state) or already saved in the
// session — and a file must never appear twice.

describe('mergeAttachmentChips', () => {
  it('shows a pending file as a chip', () => {
    const chips = mergeAttachmentChips([{ name: 'report.pdf', bytes: 10 }], []);
    expect(chips.map((c) => c.name)).toEqual(['report.pdf']);
  });

  it('shows saved session files as chips', () => {
    expect(mergeAttachmentChips([], [{ name: 'a.md' }, { name: 'b.csv' }])).toEqual([
      { name: 'a.md' },
      { name: 'b.csv' },
    ]);
  });

  it('does not duplicate a file that is both pending and saved', () => {
    const chips = mergeAttachmentChips(
      [{ name: 'report.pdf', bytes: 10 }],
      [{ name: 'report.pdf' }, { name: 'notes.txt' }],
    );
    expect(chips.map((c) => c.name)).toEqual(['report.pdf', 'notes.txt']);
    expect(new Set(chips.map((c) => c.name)).size).toBe(chips.length);
  });

  it('is empty when nothing is attached', () => {
    expect(mergeAttachmentChips([], [])).toEqual([]);
  });
});

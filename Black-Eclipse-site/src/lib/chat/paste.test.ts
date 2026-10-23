import { describe, it, expect } from 'vitest';
import { PASTE_AS_ATTACHMENT_CHARS, buildUserTurn, claimPastes, isLongPaste, pastedTextName } from './paste';

// A paste is a DOCUMENT when it is too big to belong in the composer. These
// pin the rule and the naming, so a long paste always lands as a visible
// attachment (and two pastes never collide on one name).

describe('isLongPaste', () => {
  it('treats an ordinary pasted sentence as a message', () => {
    expect(isLongPaste('analyze AAPL')).toBe(false);
    expect(isLongPaste('x'.repeat(PASTE_AS_ATTACHMENT_CHARS))).toBe(false);
  });

  it('treats a pasted document as an attachment', () => {
    expect(isLongPaste('x'.repeat(PASTE_AS_ATTACHMENT_CHARS + 1))).toBe(true);
  });

  it('ignores surrounding blank lines when measuring', () => {
    const text = `\n\n${'x'.repeat(PASTE_AS_ATTACHMENT_CHARS)}\n\n`;
    expect(isLongPaste(text)).toBe(false);
  });
});

describe('pastedTextName', () => {
  it('uses a readable, stable name', () => {
    expect(pastedTextName([])).toBe('pasted-text.txt');
  });

  it('never reuses a name already taken', () => {
    expect(pastedTextName(['pasted-text.txt'])).toBe('pasted-text-2.txt');
    expect(pastedTextName(['pasted-text.txt', 'pasted-text-2.txt'])).toBe('pasted-text-3.txt');
  });

  it('ignores unrelated attachment names', () => {
    expect(pastedTextName(['report.pdf', 'notes.md'])).toBe('pasted-text.txt');
  });
});

describe('buildUserTurn', () => {
  it('keeps a typed prompt and labels the claimed pastes', () => {
    const msg = buildUserTurn('Summarize', [{ name: 'pasted-text.txt', chars: 12, preview: 'hello' }], false);
    expect(msg?.content).toBe('Summarize');
    expect(msg?.attachments).toEqual([
      { name: 'pasted-text.txt', chars: 12, preview: 'hello', pasted: true },
    ]);
  });

  it('gives a paste-only turn a readable prompt', () => {
    const msg = buildUserTurn('  ', [{ name: 'pasted-text.txt', chars: 12, preview: 'hello' }], false);
    expect(msg?.content).toBe('Read the attached document.');
  });

  it('returns null when there is nothing to send', () => {
    expect(buildUserTurn('', [], false)).toBeNull();
  });
});

describe('claimPastes', () => {
  it('claims each paste exactly once, keeping the document in the map', () => {
    const pastes = new Map([
      ['pasted-text.txt', 'first paste'],
      ['pasted-text-2.txt', 'second paste'],
    ]);
    const claimed = new Set<string>();

    expect(claimPastes(pastes, claimed)).toEqual([
      { name: 'pasted-text.txt', text: 'first paste' },
      { name: 'pasted-text-2.txt', text: 'second paste' },
    ]);
    expect(claimPastes(pastes, claimed)).toEqual([]);
    expect(pastes.size).toBe(2);
  });
});

import { describe, it, expect } from 'vitest';
import { PASTE_AS_ATTACHMENT_CHARS, isLongPaste, pastedTextName } from './paste';

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

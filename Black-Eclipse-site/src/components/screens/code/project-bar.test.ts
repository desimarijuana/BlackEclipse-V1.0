import { describe, expect, it } from 'vitest';

import { folderLabel } from './project-bar';

// The Builds project bar names the folder a build belongs to. The label is pure,
// so it is tested without a DOM: a chosen folder shows its short name, a label
// wins, and "no project" is the neutral default (never an empty string).

describe('folderLabel', () => {
  it('uses the short folder name, on either separator', () => {
    expect(folderLabel('C:\\work\\alpha', null, 'Eclipse repo')).toBe('alpha');
    expect(folderLabel('/home/me/beta', null, 'Eclipse repo')).toBe('beta');
  });

  it('prefers an explicit label', () => {
    expect(folderLabel('/home/me/beta', '  Trading desk ', 'Eclipse repo')).toBe('Trading desk');
  });

  it('falls back for the built-in repo', () => {
    expect(folderLabel(null, null, 'Eclipse repo')).toBe('Eclipse repo');
    expect(folderLabel('', '', 'Eclipse repo')).toBe('Eclipse repo');
  });
});

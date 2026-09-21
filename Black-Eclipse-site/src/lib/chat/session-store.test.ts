import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { promises as fs } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {
  SessionError,
  deleteSessionFile,
  getSession,
  loadContextDocuments,
  readSessionFile,
  writeSessionFile,
} from './session-store';
import { SESSION_LIMITS } from './session-types';

let root: string;

beforeEach(async () => {
  root = await fs.mkdtemp(path.join(os.tmpdir(), 'be-session-'));
  process.env.BLACK_ECLIPSE_SESSION_ROOT = root;
});

afterEach(async () => {
  delete process.env.BLACK_ECLIPSE_SESSION_ROOT;
  await fs.rm(root, { recursive: true, force: true });
});

describe('session-store chat id guard', () => {
  it('rejects path traversal and separators', async () => {
    await expect(getSession('../escape')).rejects.toBeInstanceOf(SessionError);
    await expect(getSession('a/b')).rejects.toBeInstanceOf(SessionError);
    await expect(getSession('..')).rejects.toBeInstanceOf(SessionError);
    await expect(getSession('')).rejects.toBeInstanceOf(SessionError);
  });

  it('accepts a normal id and creates the folders', async () => {
    const session = await getSession('chat_123-abc');
    expect(session.files).toEqual([]);
    expect(path.basename(session.path)).toBe('chat_123-abc');
  });
});

describe('session-store file handling', () => {
  it('reports context characters available for injection', async () => {
    await writeSessionFile('c1', { name: 'a.md', bytes: Buffer.from('# hi'), kind: 'context' });
    await writeSessionFile('c1', { name: 'b.png', bytes: Buffer.from([1, 2, 3]), kind: 'context' });
    const session = await getSession('c1');
    // Only the extractable file contributes; the binary one adds nothing.
    expect(session.contextChars).toBe(4);
    expect(session.contextChars).toBeLessThanOrEqual(session.contextLimitChars);
  });

  it('writes, lists, reads and deletes a context file', async () => {
    await writeSessionFile('c1', { name: 'notes.md', bytes: Buffer.from('# hi'), kind: 'context' });
    const session = await getSession('c1');
    expect(session.files).toHaveLength(1);
    expect(session.files[0]).toMatchObject({ name: 'notes.md', kind: 'context', textExtractable: true });

    const bytes = await readSessionFile('c1', 'context', 'notes.md');
    expect(bytes.toString('utf8')).toBe('# hi');

    await deleteSessionFile('c1', 'context', 'notes.md');
    expect((await getSession('c1')).files).toHaveLength(0);
  });

  it('rejects file names that escape the session folder', async () => {
    await expect(
      writeSessionFile('c1', { name: '../evil.txt', bytes: Buffer.from('x'), kind: 'context' })
    ).rejects.toBeInstanceOf(SessionError);
    await expect(
      writeSessionFile('c1', { name: '.hidden', bytes: Buffer.from('x'), kind: 'context' })
    ).rejects.toBeInstanceOf(SessionError);
  });

  it('enforces the per-file size limit', async () => {
    const tooBig = Buffer.alloc(SESSION_LIMITS.maxFileBytes + 1);
    await expect(
      writeSessionFile('c1', { name: 'big.txt', bytes: tooBig, kind: 'context' })
    ).rejects.toBeInstanceOf(SessionError);
  });

  it('separates context and output files', async () => {
    await writeSessionFile('c1', { name: 'in.txt', bytes: Buffer.from('in'), kind: 'context' });
    await writeSessionFile('c1', { name: 'out.md', bytes: Buffer.from('out'), kind: 'output' });
    const session = await getSession('c1');
    expect(session.files.filter((f) => f.kind === 'context')).toHaveLength(1);
    expect(session.files.filter((f) => f.kind === 'output')).toHaveLength(1);
  });
});

describe('loadContextDocuments', () => {
  it('returns extracted text for extractable files and skips binaries', async () => {
    await writeSessionFile('c2', { name: 'a.md', bytes: Buffer.from('# A'), kind: 'context' });
    await writeSessionFile('c2', { name: 'b.png', bytes: Buffer.from([1, 2, 3]), kind: 'context' });
    await writeSessionFile('c2', { name: 'ignored.md', bytes: Buffer.from('# X'), kind: 'output' });

    const docs = await loadContextDocuments('c2');
    expect(docs).toHaveLength(1);
    expect(docs[0]).toEqual({ name: 'a.md', text: '# A' });
  });

  it('returns nothing for an invalid id instead of throwing', async () => {
    expect(await loadContextDocuments('../nope')).toEqual([]);
  });
});

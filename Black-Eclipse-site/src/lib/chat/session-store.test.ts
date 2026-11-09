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

  it('persists and clears file provenance, and never invents it', async () => {
    await writeSessionFile('c1', {
      name: 'chat-input.tsx',
      bytes: Buffer.from('export {}'),
      kind: 'context',
      meta: { origin: 'project', sourcePath: 'src/components/chat/chat-input.tsx', rootLabel: 'eclipse' },
    });
    await writeSessionFile('c1', { name: 'local.txt', bytes: Buffer.from('x'), kind: 'context' });

    const session = await getSession('c1');
    const projectFile = session.files.find((f) => f.name === 'chat-input.tsx');
    const localFile = session.files.find((f) => f.name === 'local.txt');
    expect(projectFile).toMatchObject({
      origin: 'project',
      sourcePath: 'src/components/chat/chat-input.tsx',
      rootLabel: 'eclipse',
    });
    // A file with no recorded provenance lists without a guessed origin.
    expect(localFile?.origin).toBeUndefined();

    await deleteSessionFile('c1', 'context', 'chat-input.tsx');
    const after = await getSession('c1');
    expect(after.files.some((f) => f.name === 'chat-input.tsx')).toBe(false);
  });


  it('rejects file names that escape the session folder', async () => {
    await expect(
      writeSessionFile('c1', { name: '../evil.txt', bytes: Buffer.from('x'), kind: 'context' })
    ).rejects.toBeInstanceOf(SessionError);
    await expect(
      writeSessionFile('c1', { name: '.hidden', bytes: Buffer.from('x'), kind: 'context' })
    ).rejects.toBeInstanceOf(SessionError);
  });

  it('accepts ordinary real-world file names', async () => {
    // These all failed under the old ASCII-only allowlist, so "attach a file"
    // broke for most files a person actually picks.
    for (const name of ['notes(1).md', 'résumé.pdf', 'Q3 [final].xlsx', 'R&D.csv', 'a+b.txt']) {
      const file = await writeSessionFile('c1', { name, bytes: Buffer.from('x'), kind: 'context' });
      expect(file.name).toBe(name);
    }
  });

  it('still refuses unsafe characters', async () => {
    for (const name of ['a/b.txt', 'a\\b.txt', 'a:b.txt', 'a*b.txt', 'nul', 'CON.txt', '  ']) {
      await expect(
        writeSessionFile('c1', { name, bytes: Buffer.from('x'), kind: 'context' })
      ).rejects.toBeInstanceOf(SessionError);
    }
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

  it('marks a shortened document so the run can state the limit', async () => {
    const big = 'a'.repeat(SESSION_LIMITS.maxDocChars + 500);
    await writeSessionFile('c3', { name: 'big.txt', bytes: Buffer.from(big, 'utf8'), kind: 'context' });

    const docs = await loadContextDocuments('c3');
    expect(docs).toHaveLength(1);
    expect(docs[0].name).toBe('big.txt');
    expect(docs[0].text.length).toBe(SESSION_LIMITS.maxDocChars);
    expect(docs[0].truncated).toBe(true);
    expect(docs[0].originalChars).toBe(big.length);
  });
});

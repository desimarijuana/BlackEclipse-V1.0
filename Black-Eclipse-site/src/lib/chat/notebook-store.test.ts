import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { promises as fs } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { readNotebook, writeNotebook } from './notebook-store';

let root = '';

function cell(overrides: Record<string, unknown> = {}) {
  return {
    id: 'nb_abc123',
    source: 'result = {"ok": True}',
    language: 'python',
    status: 'ok',
    outputs: { ok: true },
    artifacts: [],
    figure: null,
    provenance: 'computed',
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    ...overrides,
  };
}

describe('chat notebook store', () => {
  beforeEach(async () => {
    root = await fs.mkdtemp(path.join(os.tmpdir(), 'eclipse-nb-'));
    process.env.BLACK_ECLIPSE_SESSION_ROOT = root;
  });

  afterEach(async () => {
    delete process.env.BLACK_ECLIPSE_SESSION_ROOT;
    await fs.rm(root, { recursive: true, force: true });
  });

  it('round-trips cells and preserves the source verbatim', async () => {
    const source = 'total = sum([1, 2, 3])\nresult = {"total": total}';
    const saved = await writeNotebook('chat_1', [cell({ source })]);
    expect(saved.cells).toHaveLength(1);
    expect(saved.cells[0]?.source).toBe(source);

    const read = await readNotebook('chat_1');
    expect(read.cells[0]?.source).toBe(source);
    expect(read.cells[0]?.provenance).toBe('computed');
  });

  it('keeps a chart link and the chart inputs', async () => {
    await writeNotebook('chat_2', [
      cell({ chartBlockId: 'chart_1', inputs: { chart: { kind: 'line' } } }),
    ]);
    const read = await readNotebook('chat_2');
    expect(read.cells[0]?.chartBlockId).toBe('chart_1');
    expect(read.cells[0]?.inputs).toEqual({ chart: { kind: 'line' } });
  });

  it('keeps a draft cell and refuses an unsafe id', async () => {
    const saved = await writeNotebook('chat_3', [
      cell({ id: 'nb_ok' }),
      cell({ id: 'nb_empty', source: '   ' }),
    ]);
    expect(saved.cells.map((item) => item.id)).toEqual(['nb_ok', 'nb_empty']);

    await expect(writeNotebook('chat_3', [cell({ id: '../bad' })])).rejects.toThrow('invalid id');
  });

  it('does not leave a persisted running cell spinning after a reload', async () => {
    await writeNotebook('chat_4', [cell({ id: 'nb_run', status: 'running' })]);
    const read = await readNotebook('chat_4');
    expect(read.cells[0]?.status).toBe('idle');
  });

  it('returns an empty document for a conversation with no notebook', async () => {
    const read = await readNotebook('chat_missing');
    expect(read.chatId).toBe('chat_missing');
    expect(read.cells).toEqual([]);
  });
});

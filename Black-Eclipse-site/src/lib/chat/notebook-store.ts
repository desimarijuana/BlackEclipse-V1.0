// SERVER-ONLY: the per-conversation notebook document (Phase 21).
//
// It lives beside the session's transcript:
//
//   .black-eclipse/sessions/<chatId>/notebook.json
//
// The transcript records what was SAID; this file records what is being WORKED
// ON. Keeping them separate means an edit never mutates a chart block and a
// chat turn never rewrites a cell. The same chat-id validation the session
// store uses is applied by `sessionDir`.

import { promises as fs } from 'node:fs';
import path from 'node:path';
import { sessionDir } from './session-store';
import {
  NOTEBOOK_LIMITS,
  emptyNotebook,
  type NotebookArtifact,
  type NotebookCell,
  type NotebookCellStatus,
  type NotebookDocument,
  type NotebookFigure,
} from './notebook-types';

const NOTEBOOK_FILE = 'notebook.json';
const CELL_ID_RE = /^[A-Za-z0-9_-]{1,80}$/;
const STATUS = new Set<NotebookCellStatus>([
  'idle', 'running', 'ok', 'failed', 'refused', 'timed_out',
]);

function notebookPath(chatId: string): string {
  return path.join(sessionDir(chatId), NOTEBOOK_FILE);
}

function plainObject(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function artifact(value: unknown): NotebookArtifact | null {
  const row = plainObject(value);
  const name = typeof row.name === 'string' ? row.name.slice(0, 240) : '';
  if (!name) return null;
  return {
    id: typeof row.id === 'string' ? row.id.slice(0, 200) : null,
    name,
    bytes: typeof row.bytes === 'number' && Number.isFinite(row.bytes) ? row.bytes : null,
    sha256: typeof row.sha256 === 'string' ? row.sha256.slice(0, 128) : null,
    mimeType: typeof row.mimeType === 'string' ? row.mimeType.slice(0, 120) : 'application/octet-stream',
    downloadUrl: typeof row.downloadUrl === 'string' ? row.downloadUrl.slice(0, 400) : null,
  };
}

function figure(value: unknown): NotebookFigure | null {
  const row = plainObject(value);
  if (!row.kind || typeof row.kind !== 'string') return null;
  return {
    kind: row.kind.slice(0, 80),
    label: typeof row.label === 'string' ? row.label.slice(0, 80) : 'computed',
    artifact: typeof row.artifact === 'string' ? row.artifact.slice(0, 240) : null,
    series: Array.isArray(row.series)
      ? row.series.slice(0, 24).map((item) => {
          const s = plainObject(item);
          return { name: String(s.name ?? 'Series').slice(0, 120), points: Number(s.points) || 0 };
        })
      : [],
    seed: typeof row.seed === 'number' ? row.seed : null,
    isEvidence: false,
  };
}

function normalizeCell(value: unknown, chatId: string): NotebookCell | null {
  const row = plainObject(value);
  const id = typeof row.id === 'string' ? row.id : '';
  if (!CELL_ID_RE.test(id)) return null;
  // An empty source is a legal DRAFT cell; the run route is what refuses a
  // program with nothing in it. Dropping it here would make a cleared editor
  // vanish on the next reload.
  const source = typeof row.source === 'string' ? row.source : '';
  if (source.length > NOTEBOOK_LIMITS.maxSourceChars) return null;
  // A run does not survive a reload: a persisted `running` is an interrupted
  // attempt, not a live one. Report it as ready rather than spinning forever.
  const stored = (typeof row.status === 'string' && STATUS.has(row.status as NotebookCellStatus)
    ? row.status
    : 'idle') as NotebookCellStatus;
  const status: NotebookCellStatus = stored === 'running' ? 'idle' : stored;
  const now = new Date().toISOString();
  const cell: NotebookCell = {
    id,
    chatId,
    source,
    language: 'python',
    status,
    outputs: plainObject(row.outputs),
    artifacts: Array.isArray(row.artifacts)
      ? row.artifacts.map(artifact).filter((item): item is NotebookArtifact => item !== null).slice(0, 20)
      : [],
    figure: figure(row.figure),
    provenance: 'computed',
    createdAt: typeof row.createdAt === 'string' ? row.createdAt : now,
    updatedAt: typeof row.updatedAt === 'string' ? row.updatedAt : now,
  };
  if (typeof row.error === 'string' && row.error) cell.error = row.error.slice(0, 4_000);
  else cell.error = null;
  if (typeof row.chartBlockId === 'string' && row.chartBlockId) {
    cell.chartBlockId = row.chartBlockId.slice(0, 200);
  }
  if (row.inputs && typeof row.inputs === 'object' && !Array.isArray(row.inputs)) {
    cell.inputs = plainObject(row.inputs);
  }
  return cell;
}

export async function readNotebook(chatId: string): Promise<NotebookDocument> {
  try {
    const target = notebookPath(chatId);
    const stat = await fs.stat(target);
    if (stat.size > 32_000_000) return emptyNotebook(chatId);
    const raw = await fs.readFile(target, 'utf8');
    const parsed = JSON.parse(raw) as Partial<NotebookDocument> | null;
    if (!parsed || typeof parsed !== 'object') return emptyNotebook(chatId);
    const cells = Array.isArray(parsed.cells)
      ? parsed.cells
          .map((cell) => normalizeCell(cell, chatId))
          .filter((cell): cell is NotebookCell => cell !== null)
          .slice(0, NOTEBOOK_LIMITS.maxCells)
      : [];
    return {
      chatId,
      version: 1,
      cells,
      updatedAt: typeof parsed.updatedAt === 'string' ? parsed.updatedAt : new Date().toISOString(),
    };
  } catch {
    return emptyNotebook(chatId);
  }
}

export async function writeNotebook(
  chatId: string,
  cells: unknown,
): Promise<NotebookDocument> {
  const list = Array.isArray(cells) ? cells : [];
  if (list.length > NOTEBOOK_LIMITS.maxCells) {
    throw new Error(`a notebook may hold at most ${NOTEBOOK_LIMITS.maxCells} cells`);
  }
  // Refuse rather than silently drop: a dropped cell is lost work, and a clear
  // error lets the editor keep the local copy until it is shortened.
  for (const raw of list) {
    const row = plainObject(raw);
    const id = typeof row.id === 'string' ? row.id : '';
    if (!CELL_ID_RE.test(id)) throw new Error('a cell has an invalid id');
    const source = typeof row.source === 'string' ? row.source : '';
    if (source.length > NOTEBOOK_LIMITS.maxSourceChars) {
      throw new Error(`cell ${id} is longer than ${NOTEBOOK_LIMITS.maxSourceChars} characters`);
    }
    if (JSON.stringify(row.inputs ?? {}).length > 2_000_000) {
      throw new Error(`cell ${id} has more data than a cell may hold`);
    }
  }
  const normalized = list
    .map((cell) => normalizeCell(cell, chatId))
    .filter((cell): cell is NotebookCell => cell !== null)
    .slice(0, NOTEBOOK_LIMITS.maxCells);
  const document: NotebookDocument = {
    chatId,
    version: 1,
    cells: normalized,
    updatedAt: new Date().toISOString(),
  };
  const target = notebookPath(chatId);
  const text = JSON.stringify(document);
  if (text.length > 24_000_000) {
    throw new Error('the notebook is larger than a conversation may hold');
  }
  await fs.mkdir(path.dirname(target), { recursive: true });
  await fs.writeFile(target, text, 'utf8');
  return document;
}

export { notebookPath };

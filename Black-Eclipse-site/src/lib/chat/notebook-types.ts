// ── Chat notebook document (Phase 21) ───────────────────────────────────────
//
// A notebook belongs to ONE conversation. It is a sidecar beside the transcript
// (`notebook.json`), not a change to the `chart` block: a chart stays the
// canonical declarative answer, and a cell is an editable alternate view.
//
// The source is stored verbatim so an edit survives a reload. It is never
// executed by this module or by the browser — the Python runtime is the only
// executor, through the analysis sandbox.

export const NOTEBOOK_LIMITS = {
  maxCells: 100,
  maxSourceChars: 20_000,
} as const;

export type NotebookCellStatus =
  | 'idle'
  | 'running'
  | 'ok'
  | 'failed'
  | 'refused'
  | 'timed_out';

export interface NotebookArtifact {
  id: string | null;
  name: string;
  bytes: number | null;
  sha256: string | null;
  mimeType: string;
  downloadUrl: string | null;
}

export interface NotebookFigure {
  kind: string;
  label: string;
  artifact?: string | null;
  series?: Array<{ name: string; points: number }>;
  seed?: number | null;
  isEvidence: false;
}

export interface NotebookProvenance {
  kind: 'computed' | 'retrieved';
  label: string;
  detail: string;
  sourceDigest?: string | null;
  citation?: string | null;
}

export interface NotebookCell {
  id: string;
  chatId: string;
  source: string;
  language: 'python';
  status: NotebookCellStatus;
  outputs: Record<string, unknown>;
  artifacts: NotebookArtifact[];
  figure?: NotebookFigure | null;
  provenance: 'computed';
  error?: string | null;
  chartBlockId?: string;
  /** The chart's resolved spec, passed to the program as `inputs.chart`. */
  inputs?: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
}

export interface NotebookDocument {
  chatId: string;
  version: 1;
  cells: NotebookCell[];
  updatedAt: string;
}

export function emptyNotebook(chatId: string): NotebookDocument {
  return { chatId, version: 1, cells: [], updatedAt: new Date().toISOString() };
}

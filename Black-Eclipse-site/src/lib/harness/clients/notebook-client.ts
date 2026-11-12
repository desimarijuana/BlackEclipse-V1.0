// The chat notebook's browser client (Phase 21).
//
// Two boundaries:
//   * the cell DOCUMENT is chat state (`/api/chat/notebook`);
//   * running a cell is the Python runtime (`/api/harness/notebook`), which
//     owns the sandbox, the kernel and the artifact catalog.
//
// Nothing here executes code in the browser. The source travels to the runtime;
// the result comes back as outputs, artifact metadata and the `computed` label.

import type {
  NotebookArtifact,
  NotebookCell,
  NotebookDocument,
  NotebookFigure,
  NotebookProvenance,
} from '@/lib/chat/notebook-types';
import type { ChartSpec } from '@/lib/harness/charts';
import { downloadUrl as artifactDownloadUrl } from '@/lib/harness/clients/artifacts-browser';

export interface NotebookRunResult {
  status: string;
  outputs: Record<string, unknown>;
  artifacts: NotebookArtifact[];
  figure: NotebookFigure | null;
  provenance: NotebookProvenance | null;
  sourceDigest?: string;
  durationMs: number;
  code?: string | null;
  error?: string | null;
}

export interface ChartSourceResult {
  source: string;
  unsupported: string[];
  /** The resolved spec (a named `dataSource` is already filled). */
  spec?: ChartSpec;
}

async function readError(res: Response, fallback: string): Promise<string> {
  const body = (await res.json().catch(() => ({}))) as {
    error?: string;
    detail?: { message?: string } | string;
  };
  const detail = body.detail;
  if (typeof detail === 'object' && detail && 'message' in detail) return String(detail.message);
  if (typeof detail === 'string') return detail;
  return body.error ?? fallback;
}

/** Read the conversation's editable notebook. */
export async function readNotebook(chatId: string): Promise<NotebookDocument> {
  const res = await fetch(`/api/chat/notebook?chatId=${encodeURIComponent(chatId)}`, {
    cache: 'no-store',
  });
  const body = (await res.json().catch(() => ({}))) as {
    notebook?: NotebookDocument;
    error?: string;
  };
  if (!res.ok || !body.notebook) throw new Error(body.error ?? 'Notebook could not be read');
  return body.notebook;
}

/** Save the whole cell document (bounded server-side). */
export async function saveNotebook(
  chatId: string,
  cells: NotebookCell[],
): Promise<NotebookDocument> {
  const res = await fetch('/api/chat/notebook', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chatId, cells }),
    cache: 'no-store',
  });
  const body = (await res.json().catch(() => ({}))) as {
    notebook?: NotebookDocument;
    error?: string;
  };
  if (!res.ok || !body.notebook) throw new Error(body.error ?? 'Notebook could not be saved');
  return body.notebook;
}

/** Run one cell in the conversation's sandbox. */
export async function runNotebookCell(
  chatId: string,
  cellId: string,
  source: string,
  inputs: Record<string, unknown> = {},
  timeoutS = 120,
): Promise<NotebookRunResult> {
  const res = await fetch(
    `/api/harness/notebook/cells/${encodeURIComponent(cellId)}/run`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chatId, source, inputs, timeoutS }),
      cache: 'no-store',
      signal: AbortSignal.timeout(150_000),
    },
  );
  const body = (await res.json().catch(() => ({}))) as Partial<NotebookRunResult> & {
    error?: string;
    detail?: { message?: string } | string;
  };
  if (!res.ok && !body.status) {
    throw new Error(await readError(res, 'The cell could not be run'));
  }
  const artifacts = Array.isArray(body.artifacts) ? body.artifacts : [];
  return {
    status: String(body.status ?? (res.ok ? 'ok' : 'failed')),
    outputs: body.outputs && typeof body.outputs === 'object' ? body.outputs : {},
    // The runtime returns a same-origin `/artifacts/...` path; the browser goes
    // through the front door's `/api/artifacts/...` proxy. Prefer the id.
    artifacts: artifacts.map((artifact) => ({
      ...artifact,
      downloadUrl: artifact.id ? artifactDownloadUrl(artifact.id) : artifact.downloadUrl,
    })),
    figure: body.figure ?? null,
    provenance: body.provenance ?? null,
    sourceDigest: body.sourceDigest,
    durationMs: Number(body.durationMs) || 0,
    code: body.code ?? null,
    error: body.error ?? null,
  };
}

/** Drop the conversation's warm kernel. */
export async function restartNotebookKernel(chatId: string): Promise<void> {
  const res = await fetch('/api/harness/notebook/kernel/restart', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chatId }),
    cache: 'no-store',
  });
  if (!res.ok) throw new Error(await readError(res, 'The notebook could not be restarted'));
}

/** Generate an editable matplotlib starting script from a resolved chart spec. */
export async function generateChartSource(spec: ChartSpec): Promise<ChartSourceResult> {
  const res = await fetch('/api/harness/charts/code', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(spec),
    cache: 'no-store',
  });
  const body = (await res.json().catch(() => ({}))) as {
    source?: string;
    unsupported?: string[];
    spec?: ChartSpec;
    error?: string;
  };
  if (!res.ok || typeof body.source !== 'string') {
    const message = await readError(res, 'The chart code could not be generated');
    throw new Error(message);
  }
  return {
    source: body.source,
    unsupported: Array.isArray(body.unsupported) ? body.unsupported : [],
    ...(body.spec ? { spec: body.spec } : {}),
  };
}

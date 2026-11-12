'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { Code } from '@/lib/icons';
import { useT } from '@/lib/i18n/use-t';
import type { NotebookCell } from '@/lib/chat/notebook-types';
import {
  readNotebook,
  restartNotebookKernel,
  runNotebookCell,
  saveNotebook,
} from '@/lib/harness/clients/notebook-client';
import { NotebookPanel } from './notebook-panel';

export interface ChartCellSeed {
  source: string;
  chartBlockId?: string;
  inputs: Record<string, unknown>;
  unsupported?: string[];
}

export interface NotebookContextValue {
  chatId: string | null;
  cells: NotebookCell[];
  isOpen: boolean;
  busy: boolean;
  open: () => void;
  close: () => void;
  addCell: () => void;
  createChartCell: (seed: ChartCellSeed) => void;
  updateSource: (id: string, source: string) => void;
  runCell: (id: string) => void;
  deleteCell: (id: string) => void;
  restart: () => void;
}

const NotebookContext = createContext<NotebookContextValue | null>(null);

/** The notebook for the conversation around this subtree, or null outside it. */
export function useNotebook(): NotebookContextValue | null {
  return useContext(NotebookContext);
}

function newId(): string {
  const random = typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID().replace(/-/g, '').slice(0, 16)
    : Math.random().toString(36).slice(2, 18);
  return `nb_${random}`;
}

function templateSource(): string {
  return [
    '# A cell in this conversation.',
    '# Variables you define here stay available to later cells.',
    'total = 1 + 1',
    'result = {"total": total}',
  ].join('\n');
}

function makeCell(chatId: string, source: string, extra: Partial<NotebookCell> = {}): NotebookCell {
  const now = new Date().toISOString();
  return {
    id: newId(),
    chatId,
    source,
    language: 'python',
    status: 'idle',
    outputs: {},
    artifacts: [],
    figure: null,
    provenance: 'computed',
    createdAt: now,
    updatedAt: now,
    ...extra,
  };
}

/** A small composer/header action that opens the current notebook. */
export function NotebookButton({ className }: { className?: string }) {
  const t = useT();
  const notebook = useNotebook();
  if (!notebook || !notebook.chatId) return null;
  return (
    <button
      type="button"
      onClick={notebook.open}
      title={t('notebook.title')}
      className={className ?? 'flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] text-muted-foreground transition-colors hover:bg-white/5 hover:text-foreground'}
    >
      <Code size={12} />
      <span className="hidden sm:inline">{t('notebook.title')}</span>
      {notebook.cells.length > 0 && (
        <span className="text-muted-foreground/60">{notebook.cells.length}</span>
      )}
    </button>
  );
}

export function NotebookProvider({ chatId, children }: { chatId: string | null; children: ReactNode }) {
  const t = useT();
  const [cells, setCells] = useState<NotebookCell[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const cellsRef = useRef<NotebookCell[]>([]);
  cellsRef.current = cells;
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!chatId) {
      setCells([]);
      return () => { cancelled = true; };
    }
    void readNotebook(chatId)
      .then((document) => {
        if (!cancelled) setCells(document.cells);
      })
      .catch(() => {
        if (!cancelled) setNotice(t('notebook.saveFailed'));
      });
    return () => {
      cancelled = true;
      if (saveTimer.current) clearTimeout(saveTimer.current);
    };
  }, [chatId, t]);

  const persist = useCallback((next: NotebookCell[], immediate = true) => {
    if (!chatId) return;
    const write = () => {
      void saveNotebook(chatId, next).catch(() => setNotice(t('notebook.saveFailed')));
    };
    if (saveTimer.current) clearTimeout(saveTimer.current);
    if (immediate) write();
    else saveTimer.current = setTimeout(write, 600);
  }, [chatId, t]);

  const commit = useCallback((next: NotebookCell[], immediate = true) => {
    setCells(next);
    cellsRef.current = next;
    persist(next, immediate);
  }, [persist]);

  const open = useCallback(() => setIsOpen(true), []);
  const close = useCallback(() => setIsOpen(false), []);

  const addCell = useCallback(() => {
    if (!chatId) return;
    commit([...cellsRef.current, makeCell(chatId, templateSource())]);
    setIsOpen(true);
  }, [chatId, commit]);

  const createChartCell = useCallback((seed: ChartCellSeed) => {
    if (!chatId) return;
    const cell = makeCell(chatId, seed.source, {
      chartBlockId: seed.chartBlockId,
      inputs: seed.inputs,
    });
    commit([...cellsRef.current, cell]);
    setIsOpen(true);
    setNotice(
      seed.unsupported?.length
        ? t('notebook.unsupported', { what: seed.unsupported.join(', ') })
        : t('notebook.startingScript'),
    );
  }, [chatId, commit, t]);

  const updateSource = useCallback((id: string, source: string) => {
    const next = cellsRef.current.map((cell) =>
      cell.id === id ? { ...cell, source, updatedAt: new Date().toISOString() } : cell,
    );
    commit(next, false);
  }, [commit]);

  const deleteCell = useCallback((id: string) => {
    commit(cellsRef.current.filter((cell) => cell.id !== id));
  }, [commit]);

  const runCell = useCallback((id: string) => {
    if (!chatId || busy) return;
    const cell = cellsRef.current.find((item) => item.id === id);
    if (!cell) return;
    setBusy(true);
    setNotice(null);
    const running = cellsRef.current.map((item) =>
      item.id === id ? { ...item, status: 'running' as const, error: null } : item,
    );
    commit(running);
    void runNotebookCell(chatId, cell.id, cell.source, cell.inputs ?? {})
      .then((result) => {
        const next = cellsRef.current.map((item) =>
          item.id === id
            ? {
                ...item,
                status: (result.status || 'failed') as NotebookCell['status'],
                outputs: result.outputs,
                artifacts: result.artifacts,
                figure: result.figure,
                error: result.error,
                updatedAt: new Date().toISOString(),
              }
            : item,
        );
        commit(next);
      })
      .catch((err: unknown) => {
        const message = err instanceof Error ? err.message : t('notebook.runFailed');
        const next = cellsRef.current.map((item) =>
          item.id === id
            ? { ...item, status: 'failed' as const, error: message, updatedAt: new Date().toISOString() }
            : item,
        );
        commit(next);
      })
      .finally(() => setBusy(false));
  }, [busy, chatId, commit, t]);

  const restart = useCallback(() => {
    if (!chatId || busy) return;
    setBusy(true);
    setNotice(null);
    void restartNotebookKernel(chatId)
      .then(() => setNotice(t('notebook.restarted')))
      .catch(() => setNotice(t('notebook.restartFailed')))
      .finally(() => setBusy(false));
  }, [busy, chatId, t]);

  return (
    <NotebookContext.Provider
      value={{
        chatId,
        cells,
        isOpen,
        busy,
        open,
        close,
        addCell,
        createChartCell,
        updateSource,
        runCell,
        deleteCell,
        restart,
      }}
    >
      {children}
      {isOpen && (
        <NotebookPanel
          cells={cells}
          busy={busy}
          notice={notice}
          onClose={close}
          onAdd={addCell}
          onRun={runCell}
          onChange={updateSource}
          onDelete={deleteCell}
          onRestart={restart}
        />
      )}
    </NotebookContext.Provider>
  );
}

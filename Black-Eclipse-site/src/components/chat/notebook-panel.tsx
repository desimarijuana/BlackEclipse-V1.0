'use client';

import { createPortal } from 'react-dom';
import { Code, Loader2, Plus, RefreshCw, X } from '@/lib/icons';
import { useT } from '@/lib/i18n/use-t';
import type { NotebookCell } from '@/lib/chat/notebook-types';
import { NotebookCellView } from './notebook-cell';

export interface NotebookPanelProps {
  cells: NotebookCell[];
  busy: boolean;
  notice: string | null;
  onClose: () => void;
  onAdd: () => void;
  onRun: (id: string) => void;
  onChange: (id: string, source: string) => void;
  onDelete: (id: string) => void;
  onRestart: () => void;
}

/**
 * The conversation's notebook. It is PORTALED to <body> for the same reason the
 * chart focus view is: inside the chat it would sit under the app header and its
 * own toolbar would collide with the top bar. The panel is a side sheet, not a
 * dialog over the transcript, so the chat stays readable beside it.
 */
export function NotebookPanel(props: NotebookPanelProps) {
  const t = useT();
  if (typeof document === 'undefined') return null;

  return createPortal(
    <div className="fixed inset-0 z-[280] flex justify-end bg-black/35" role="dialog" aria-modal="true" aria-label={t('notebook.title')}>
      <button type="button" aria-label={t('notebook.close')} className="flex-1 cursor-default" onClick={props.onClose} />
      <aside className="glass-card-strong flex h-full w-full max-w-[620px] flex-col border-l border-white/10 shadow-2xl shadow-black/50">
        <header className="flex items-center gap-2 border-b border-white/10 px-3 py-2.5">
          <Code size={15} className="text-primary" />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-foreground">{t('notebook.title')}</p>
            <p className="truncate text-[10px] text-muted-foreground">{t('notebook.subtitle')}</p>
          </div>
          <button
            type="button"
            onClick={props.onRestart}
            disabled={props.busy}
            className="flex items-center gap-1 rounded-md border border-border/50 px-2 py-1 text-[10px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:opacity-40"
          >
            <RefreshCw size={11} />
            {t('notebook.restart')}
          </button>
          <button
            type="button"
            onClick={props.onClose}
            aria-label={t('notebook.close')}
            className="flex h-7 w-7 items-center justify-center rounded-md border border-border/50 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <X size={13} />
          </button>
        </header>

        <div className="flex-1 space-y-2 overflow-y-auto p-2.5">
          {props.cells.length === 0 ? (
            <p className="rounded-xl border border-dashed border-border/40 p-4 text-center text-xs text-muted-foreground">
              {t('notebook.empty')}
            </p>
          ) : (
            props.cells.map((cell, index) => (
              <NotebookCellView
                key={cell.id}
                cell={cell}
                index={index}
                busy={props.busy}
                onChange={props.onChange}
                onRun={props.onRun}
                onDelete={props.onDelete}
              />
            ))
          )}
          {props.notice && (
            <p className="rounded-md border border-border/30 bg-white/5 px-2 py-1.5 text-[10px] text-muted-foreground">
              {props.notice}
            </p>
          )}
        </div>

        <footer className="border-t border-white/10 p-2.5">
          <button
            type="button"
            onClick={props.onAdd}
            disabled={props.busy}
            className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-border/50 px-3 py-2 text-xs text-foreground transition-colors hover:bg-accent disabled:opacity-40"
          >
            {props.busy ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
            {t('notebook.addCell')}
          </button>
        </footer>
      </aside>
    </div>,
    document.body,
  );
}

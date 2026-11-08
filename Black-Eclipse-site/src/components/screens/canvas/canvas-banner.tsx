'use client';

// ── Canvas inline banner ────────────────────────────────────────────────────
// Opening a response in Canvas MOVES it: the message body is replaced by this
// one compact banner (ChatGPT-style), and the content lives only in the Canvas
// surface. "Show in chat" restores the body; "Edit" saves the snapshot as a
// real canvas artifact first.

import { useCallback, useState } from 'react';
import { ChevronLeft, Loader2, SquarePen } from '@/lib/icons';
import { makeCanvasEditable } from '@/lib/canvas/save-to-edit';
import { useCommandStore } from '@/lib/search/store';

function useCanvasTitle(): string {
  return useCommandStore((s) => s.canvasSource?.title ?? (s.pendingCanvasArtifactId ? 'Canvas artifact' : 'Canvas'));
}

function useCanEdit(): boolean {
  return useCommandStore((s) => Boolean(s.canvasView && !s.canvasView.editable));
}

function useEditCanvas() {
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const edit = useCallback(async () => {
    if (editing) return;
    setEditing(true);
    setError(null);
    try {
      await makeCanvasEditable();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not open the editor');
    } finally {
      setEditing(false);
    }
  }, [editing]);
  return { editing, error, edit };
}

/** The compact card that replaces a message body while it is open in Canvas. */
export function CanvasInlineNotice({
  title: titleProp,
  canEdit: canEditProp,
  onClose,
}: {
  /** Test/embed override; defaults to the live store. */
  title?: string;
  canEdit?: boolean;
  onClose?: () => void;
} = {}) {
  const storeTitle = useCanvasTitle();
  const closeStore = useCommandStore((s) => s.closeCanvas);
  const storeCanEdit = useCanEdit();
  const title = titleProp ?? storeTitle;
  const canEdit = canEditProp ?? storeCanEdit;
  const close = onClose ?? closeStore;
  const { editing, error, edit } = useEditCanvas();

  return (
    <div className="glass-card-subtle mt-2 flex w-full flex-wrap items-center gap-x-2 gap-y-1 rounded-xl border border-primary/25 px-3 py-2.5 text-[12px]">
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-primary/15 text-primary">
        <SquarePen size={14} />
      </span>
      <span className="min-w-0 flex-1 truncate text-muted-foreground" title={title}>
        This response is open in <span className="font-medium text-foreground/85">Canvas</span>
        <span className="text-muted-foreground/60"> · </span>
        {title}
      </span>
      {error ? <span className="text-[10.5px] text-amber-300/90" role="alert">{error}</span> : null}
      {canEdit ? (
        <button
          type="button"
          onClick={() => void edit()}
          disabled={editing}
          className="inline-flex h-7 shrink-0 items-center gap-1.5 rounded-lg border border-border/40 px-2.5 text-[11px] text-foreground transition-colors hover:bg-accent disabled:opacity-50"
        >
          {editing ? <Loader2 size={12} className="animate-spin" /> : <SquarePen size={12} />}
          {editing ? 'Opening…' : 'Edit'}
        </button>
      ) : null}
      <button
        type="button"
        onClick={close}
        className="inline-flex h-7 shrink-0 items-center gap-1 rounded-lg px-2 text-[11px] text-primary transition-colors hover:bg-primary/10"
      >
        <ChevronLeft size={12} /> Show in chat
      </button>
    </div>
  );
}

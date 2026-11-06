'use client';

// ── Canvas banner + inline notice ───────────────────────────────────────────
// When a response moves into Canvas, the chat keeps its shape: a page banner
// says what is open, and the message body becomes a compact notice. Both can
// restore the response in one click, and both can start editing (which saves
// the snapshot as a real canvas artifact first).

import { useCallback, useState } from 'react';
import { ChevronLeft, Loader2, SquarePen, X } from '@/lib/icons';
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

/** The banner at the top of the ChatBot page while Canvas is open. */
export function CanvasPageBanner({
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
    <div
      role="region"
      aria-label="Canvas open"
      className="glass-card-subtle z-20 mb-2 flex w-full shrink-0 flex-wrap items-center gap-x-2 gap-y-1 rounded-xl border border-primary/25 px-3 py-2 text-[12px]"
    >
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-primary/15 text-primary">
        <SquarePen size={14} />
      </span>
      <span className="shrink-0 font-semibold text-primary">Canvas</span>
      <span className="min-w-0 flex-1 truncate text-foreground/85" title={title} aria-live="polite">
        {title}
      </span>
      {error ? <span className="text-[10.5px] text-amber-300/90" role="alert">{error}</span> : null}
      {canEdit ? (
        <button
          type="button"
          onClick={() => void edit()}
          disabled={editing}
          className="inline-flex h-7 shrink-0 items-center gap-1.5 rounded-lg border border-border/40 px-2.5 text-[11.5px] text-foreground transition-colors hover:bg-accent disabled:opacity-50"
        >
          {editing ? <Loader2 size={12} className="animate-spin" /> : <SquarePen size={12} />}
          {editing ? 'Opening…' : 'Edit'}
        </button>
      ) : null}
      <button
        type="button"
        onClick={close}
        className="inline-flex h-7 shrink-0 items-center gap-1 rounded-lg px-2 text-[11.5px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
      >
        <ChevronLeft size={12} /> Show in chat
      </button>
      <button
        type="button"
        onClick={close}
        aria-label="Close Canvas"
        title="Close Canvas"
        className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
      >
        <X size={14} />
      </button>
    </div>
  );
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
    <div className="glass-card-subtle mt-2 flex w-full flex-wrap items-center gap-x-2 gap-y-1 rounded-xl border border-primary/25 px-3 py-2 text-[11.5px]">
      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-primary/15 text-primary">
        <SquarePen size={12} />
      </span>
      <span className="min-w-0 flex-1 truncate text-muted-foreground" title={title}>
        This response is open in <span className="font-medium text-foreground/85">Canvas</span> · {title}
      </span>
      {error ? <span className="text-[10.5px] text-amber-300/90" role="alert">{error}</span> : null}
      {canEdit ? (
        <button
          type="button"
          onClick={() => void edit()}
          disabled={editing}
          className="inline-flex h-6 shrink-0 items-center gap-1 rounded-lg border border-border/40 px-2 text-[10.5px] text-foreground transition-colors hover:bg-accent disabled:opacity-50"
        >
          {editing ? <Loader2 size={11} className="animate-spin" /> : <SquarePen size={11} />}
          {editing ? 'Opening…' : 'Edit'}
        </button>
      ) : null}
      <button
        type="button"
        onClick={close}
        className="inline-flex h-6 shrink-0 items-center gap-1 rounded-lg px-1.5 text-[10.5px] text-primary transition-colors hover:bg-primary/10"
      >
        <ChevronLeft size={11} /> Show in chat
      </button>
    </div>
  );
}

'use client';

// ─── Canvas dock — the right-hand reading surface ────────────────────────────
// A real sibling column in the shell row (NOT an overlay), so the header and the
// active tab shrink to make room. Viewer-first: it renders chat content
// (markdown / code / report / url / image) at reading width; when the view is
// backed by a canvas artifact it hosts the editable CanvasScreen instead.

import { useCallback, useEffect, useRef, useState } from 'react';
import dynamic from 'next/dynamic';
import { FileJson, FileText, Loader2, SquareCode, SquarePen, X } from '@/lib/icons';
import type { CanvasContentKind } from '@/lib/canvas/content';
import { createCanvasArtifact } from '@/lib/harness/canvas-client';
import { responseToJson } from '@/lib/response/export';
import { useCommandStore } from '@/lib/search/store';
import { CanvasViewer } from './canvas-viewer';

const CanvasScreen = dynamic(
  () => import('./canvas-screen').then((m) => m.CanvasScreen),
  { ssr: false },
);

const WIDTH_KEY = 'be_canvas_dock_width';
const MIN_WIDTH = 340;
const MAX_WIDTH = 920;

function loadWidth(): number {
  if (typeof window === 'undefined') return 520;
  const raw = Number(localStorage.getItem(WIDTH_KEY));
  return Number.isFinite(raw) && raw >= MIN_WIDTH && raw <= MAX_WIDTH ? raw : 520;
}

function KindIcon({ kind }: { kind: CanvasContentKind }) {
  if (kind === 'code') return <SquareCode className="h-4 w-4" />;
  if (kind === 'report') return <FileJson className="h-4 w-4" />;
  return <FileText className="h-4 w-4" />;
}

const KIND_LABEL: Record<CanvasContentKind, string> = {
  markdown: 'Document',
  code: 'Code',
  report: 'Report',
  url: 'Web page',
  image: 'Image',
};

export function CanvasDock() {
  const content = useCommandStore((s) => s.canvasView);
  const artifactId = useCommandStore((s) => s.pendingCanvasArtifactId);
  const close = useCommandStore((s) => s.closeCanvas);
  const openCanvas = useCommandStore((s) => s.openCanvas);

  const [width, setWidth] = useState(loadWidth);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const dragging = useRef(false);

  useEffect(() => {
    const onMove = (event: PointerEvent) => {
      if (!dragging.current) return;
      const next = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, window.innerWidth - event.clientX));
      setWidth(next);
    };
    const onUp = () => {
      if (!dragging.current) return;
      dragging.current = false;
      try { localStorage.setItem(WIDTH_KEY, String(width)); } catch { /* ignore quota */ }
      document.body.style.cursor = '';
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    return () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
  }, [width]);

  const openFollowup = useCallback((prompt: string) => {
    useCommandStore.getState().dispatch({ tab: 'chat', params: { prompt } });
  }, []);

  // Turn ephemeral response content into a real, editable canvas artifact.
  const saveToEdit = useCallback(async () => {
    if (!content || content.editable) return;
    setSaving(true);
    setSaveError(null);
    try {
      const kind = content.kind === 'code' ? 'code' : content.kind === 'report' ? 'visual' : 'document';
      const text = content.kind === 'code'
        ? content.code?.text ?? ''
        : content.kind === 'report' && content.response
          ? responseToJson(content.response)
          : content.markdown ?? '';
      const snap = await createCanvasArtifact({
        name: content.title,
        kind,
        language: content.kind === 'code' ? content.code?.language : undefined,
        content: text,
      });
      openCanvas(snap.artifactId);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Could not save this to Canvas');
    } finally {
      setSaving(false);
    }
  }, [content, openCanvas]);

  // Artifact-backed: the editor owns its own card + header.
  if (artifactId) {
    return (
      <div className="hidden h-full shrink-0 md:flex" style={{ width }}>
        <CanvasScreen inline initialArtifactId={artifactId} onClose={close} />
      </div>
    );
  }

  return (
    <aside
      className="relative flex h-full w-full shrink-0 flex-col md:w-auto"
      style={{ width: typeof window !== 'undefined' && window.innerWidth >= 768 ? width : undefined }}
      aria-label="Eclipse Canvas"
    >
      {/* Drag handle — lets the user resize the reading surface. */}
      <div
        role="separator"
        aria-orientation="vertical"
        onPointerDown={() => { dragging.current = true; document.body.style.cursor = 'col-resize'; }}
        className="absolute inset-y-0 left-0 z-10 hidden w-1.5 -translate-x-1/2 cursor-col-resize bg-transparent transition-colors hover:bg-primary/30 md:block"
      />
      <section className="glass-card flex h-full min-h-0 w-full flex-col overflow-hidden rounded-2xl">
        <header className="flex shrink-0 items-center gap-2 border-b border-border/15 px-3 py-2">
          {content ? <span className="text-primary"><KindIcon kind={content.kind} /></span> : <SquarePen className="h-4 w-4 text-primary" />}
          <span className="min-w-0 flex-1 truncate text-sm font-semibold text-foreground">
            {content?.title ?? 'Canvas'}
          </span>
          {content ? (
            <span className="shrink-0 rounded-full bg-accent/30 px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground/70">
              {KIND_LABEL[content.kind]}
            </span>
          ) : null}
          {content && !content.editable ? (
            <button
              type="button"
              onClick={() => void saveToEdit()}
              disabled={saving}
              className="shrink-0 rounded-full border border-border/40 px-2.5 py-0.5 text-[11px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:opacity-50"
              title="Save this view as an editable canvas artifact"
            >
              {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : 'Save to edit'}
            </button>
          ) : null}
          <button
            type="button"
            onClick={close}
            aria-label="Close Canvas"
            title="Close Canvas"
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <X size={15} />
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          {saveError ? <p className="mb-3 text-xs text-rose-300">{saveError}</p> : null}
          {content ? (
            <CanvasViewer content={content} onFollowup={openFollowup} />
          ) : (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
              <SquarePen className="h-7 w-7 text-muted-foreground/50" />
              <p className="text-sm font-medium text-foreground">Nothing open in Canvas</p>
              <p className="max-w-[38ch] text-xs text-muted-foreground/70">
                Use <span className="text-foreground/80">Open in Canvas</span> on a chat response to read
                it here at full width.
              </p>
            </div>
          )}
        </div>
      </section>
    </aside>
  );
}

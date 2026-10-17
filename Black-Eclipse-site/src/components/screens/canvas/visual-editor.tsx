'use client';

// ─── Canvas visual editor (Eclipse response envelope) ─────────────────────────
// Content is the JSON string of an Eclipse response envelope. A plain textarea
// is the source of truth (SSR-safe, no heavy bundle here); the live preview
// renders through the existing Universal Response Renderer. Invalid JSON shows a
// clear error instead of crashing the renderer.

import { useEffect, useMemo, useState, type UIEvent } from 'react';
import { AlertTriangle } from '@/lib/icons';
import { parseResponsePayload } from '@/lib/response/contract';
import { ResponseView } from '@/components/response/response-view';
import { parseJsonStrict, type CanvasSelection } from './canvas-utils';

export interface VisualEditorProps {
  content: string;
  editable?: boolean;
  onChange: (next: string) => void;
  onSelectionChange?: (selection: CanvasSelection | null) => void;
}

export default function VisualEditor({ content, editable = true, onChange, onSelectionChange }: VisualEditorProps) {
  const [previewSource, setPreviewSource] = useState(content);
  useEffect(() => {
    const id = window.setTimeout(() => setPreviewSource(content), 500);
    return () => window.clearTimeout(id);
  }, [content]);

  const parsed = useMemo(() => parseJsonStrict(previewSource), [previewSource]);
  const decoded = useMemo(
    () => (parsed.ok ? { response: parseResponsePayload(parsed.value) } : null),
    [parsed],
  );

  const handleSelect = (e: UIEvent<HTMLTextAreaElement>) => {
    if (!onSelectionChange) return;
    const el = e.currentTarget;
    const { selectionStart: start, selectionEnd: end } = el;
    onSelectionChange(start !== end ? { start, end, text: el.value.slice(start, end) } : null);
  };

  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 lg:grid-cols-2">
      <div className="flex min-h-[40vh] flex-col gap-2">
        <label className="text-[11px] uppercase tracking-wide text-muted-foreground/60" htmlFor="canvas-visual-source">
          Envelope JSON
        </label>
        <textarea
          id="canvas-visual-source"
          aria-label="Envelope JSON"
          value={content}
          readOnly={!editable}
          spellCheck={false}
          onChange={(e) => onChange(e.target.value)}
          onSelect={handleSelect}
          onKeyUp={handleSelect}
          className="flex-1 resize-none rounded-lg glass-card-subtle p-3 font-mono text-[12px] leading-relaxed text-foreground/90 outline-none"
        />
      </div>
      <div className="flex min-h-[40vh] flex-col gap-2">
        <span className="text-[11px] uppercase tracking-wide text-muted-foreground/60">Live preview</span>
        <div className="flex-1 overflow-y-auto rounded-lg glass-card-subtle p-4">
          {previewSource.trim() === '' ? (
            <p className="text-sm text-muted-foreground/60">Add envelope JSON to preview.</p>
          ) : !parsed.ok ? (
            <div className="flex items-start gap-2 rounded-lg border border-rose-500/30 p-3 text-xs text-rose-300">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <div>
                <p className="font-medium">Preview unavailable — invalid JSON.</p>
                <p className="mt-1 font-mono text-[11px] text-rose-300/80">{parsed.error}</p>
              </div>
            </div>
          ) : decoded ? (
            <ResponseView response={decoded.response} />
          ) : null}
        </div>
      </div>
    </div>
  );
}

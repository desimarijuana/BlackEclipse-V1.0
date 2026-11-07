'use client';

// ─── Canvas visual editor (Eclipse response envelope) ─────────────────────────
// One compact, scrollable panel. Three tabs: Blocks (default), Source JSON and
// Preview. Editing a block changes only that element; the live preview is a tab,
// not a second half-page column.
//
// The content is the JSON string of an Eclipse response envelope. Invalid JSON
// shows a clear message instead of crashing the renderer.

import { useMemo, useState, type UIEvent } from 'react';
import { AlertTriangle, Plus, SquarePen, Trash2 } from '@/lib/icons';
import { parseResponsePayload } from '@/lib/response/contract';
import { ResponseView } from '@/components/response/response-view';
import { cn } from '@/lib/utils';
import { parseJsonStrict, type CanvasSelection } from './canvas-utils';

export interface VisualEditorProps {
  content: string;
  editable?: boolean;
  onChange: (next: string) => void;
  onSelectionChange?: (selection: CanvasSelection | null) => void;
  /** Default tab; `preview` shows the rendered document first. */
  defaultMode?: 'blocks' | 'source' | 'preview';
}

type Envelope = Record<string, unknown> & { blocks?: unknown[] };
type Mode = 'blocks' | 'source' | 'preview';

const SUMMARY_KEYS = ['title', 'markdown', 'text', 'label', 'summary', 'name', 'body', 'content', 'description'];

function blockSummary(block: unknown): string {
  if (!block || typeof block !== 'object') return String(block);
  const record = block as Record<string, unknown>;
  for (const key of SUMMARY_KEYS) {
    const value = record[key];
    if (typeof value === 'string' && value.trim()) return value.trim().replace(/\s+/g, ' ').slice(0, 120);
  }
  try {
    return JSON.stringify(block).slice(0, 120);
  } catch {
    return '';
  }
}

function blockType(block: unknown): string {
  if (!block || typeof block !== 'object') return 'block';
  const type = (block as Record<string, unknown>).type;
  return typeof type === 'string' && type.trim() ? type : 'block';
}

export default function VisualEditor({ content, editable = true, onChange, onSelectionChange, defaultMode = 'preview' }: VisualEditorProps) {
  const [mode, setMode] = useState<Mode>(defaultMode);
  const [editing, setEditing] = useState<number | null>(null);
  const [draft, setDraft] = useState('');
  const [draftError, setDraftError] = useState<string | null>(null);

  const parsed = useMemo(() => parseJsonStrict(content), [content]);
  const envelope = useMemo<Envelope | null>(() => {
    if (!parsed.ok || !parsed.value || typeof parsed.value !== 'object' || Array.isArray(parsed.value)) return null;
    return parsed.value as Envelope;
  }, [parsed]);
  const blocks = Array.isArray(envelope?.blocks) ? (envelope!.blocks as unknown[]) : null;

  const preview = useMemo(() => {
    if (!parsed.ok) return null;
    try {
      return parseResponsePayload(parsed.value);
    } catch {
      return null;
    }
  }, [parsed]);

  const commit = (nextBlocks: unknown[]) => {
    if (!envelope) return;
    onChange(JSON.stringify({ ...envelope, blocks: nextBlocks }, null, 2));
  };

  const startEdit = (index: number) => {
    if (!blocks) return;
    setEditing(index);
    setDraftError(null);
    setDraft(JSON.stringify(blocks[index], null, 2));
    setMode('blocks');
  };

  const saveEdit = () => {
    if (!blocks || editing == null) return;
    try {
      const value = JSON.parse(draft);
      if (!value || typeof value !== 'object' || Array.isArray(value)) {
        throw new Error('A block must be a JSON object.');
      }
      const next = [...blocks];
      next[editing] = value;
      commit(next);
      setEditing(null);
      setDraftError(null);
    } catch (err) {
      setDraftError(err instanceof Error ? err.message : 'That block is not valid JSON.');
    }
  };

  const removeBlock = (index: number) => {
    if (!blocks) return;
    commit(blocks.filter((_, i) => i !== index));
    if (editing === index) setEditing(null);
  };

  const addBlock = () => {
    if (!blocks) return;
    const next = [...blocks, { type: 'markdown', markdown: 'New section' }];
    commit(next);
    setEditing(next.length - 1);
    setDraft(JSON.stringify(next[next.length - 1], null, 2));
    setDraftError(null);
    setMode('blocks');
  };

  const handleSelect = (e: UIEvent<HTMLTextAreaElement>) => {
    if (!onSelectionChange) return;
    const el = e.currentTarget;
    const { selectionStart: start, selectionEnd: end } = el;
    onSelectionChange(start !== end ? { start, end, text: el.value.slice(start, end) } : null);
  };

  const tabClass = (active: boolean) =>
    cn(
      'rounded-md px-2 py-1 text-[11px] transition-colors',
      active ? 'bg-accent text-foreground' : 'text-muted-foreground hover:bg-accent/50 hover:text-foreground',
    );

  const showBlocks = mode === 'blocks' && blocks;

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      <div className="flex shrink-0 flex-wrap items-center gap-1" role="tablist" aria-label="Envelope editor mode">
        <button type="button" role="tab" aria-selected={mode === 'blocks'} className={tabClass(mode === 'blocks')} onClick={() => setMode('blocks')}>
          Blocks
        </button>
        <button type="button" role="tab" aria-selected={mode === 'source'} className={tabClass(mode === 'source')} onClick={() => setMode('source')}>
          Source JSON
        </button>
        <button type="button" role="tab" aria-selected={mode === 'preview'} className={tabClass(mode === 'preview')} onClick={() => setMode('preview')}>
          Preview
        </button>
        {blocks ? <span className="ml-auto text-[10px] text-muted-foreground/60">{blocks.length} blocks</span> : null}
      </div>

      {!parsed.ok ? (
        <p className="shrink-0 rounded-md border border-rose-500/25 bg-rose-500/5 px-2 py-1 text-[10.5px] text-rose-300" role="alert">
          invalid JSON — use Source JSON to fix it.
        </p>
      ) : null}

      <div className="min-h-0 flex-1 overflow-y-auto rounded-lg glass-card-subtle p-2">
        {showBlocks ? (
          <div className="flex flex-col gap-1.5">
            {blocks!.map((block, index) => {
              const type = blockType(block);
              const isEditing = editing === index;
              return (
                <div key={index} className="rounded-md border border-border/40 bg-black/10">
                  <div className="flex items-center gap-2 px-2 py-1.5">
                    <span className="shrink-0 rounded border border-border/40 px-1 py-0.5 font-mono text-[9px] uppercase tracking-wide text-muted-foreground/70">
                      {type}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-[11.5px] text-foreground/80" title={blockSummary(block)}>
                      {blockSummary(block)}
                    </span>
                    {editable && !isEditing ? (
                      <>
                        <button
                          type="button"
                          onClick={() => startEdit(index)}
                          className="inline-flex h-6 items-center gap-1 rounded px-1.5 text-[10.5px] text-foreground hover:bg-accent"
                        >
                          <SquarePen size={11} /> Edit
                        </button>
                        <button
                          type="button"
                          onClick={() => removeBlock(index)}
                          aria-label={`Delete ${type} block`}
                          className="inline-flex h-6 w-6 items-center justify-center rounded text-muted-foreground hover:bg-rose-500/10 hover:text-rose-300"
                        >
                          <Trash2 size={12} />
                        </button>
                      </>
                    ) : null}
                  </div>
                  {isEditing ? (
                    <div className="border-t border-border/30 p-2">
                      <textarea
                        value={draft}
                        readOnly={!editable}
                        spellCheck={false}
                        onChange={(e) => setDraft(e.target.value)}
                        aria-label={`Edit ${type} block`}
                        className="h-36 w-full resize-y rounded border border-border/40 bg-black/20 p-2 font-mono text-[11px] leading-relaxed text-foreground/90 outline-none focus:border-primary"
                      />
                      {draftError ? <p className="mt-1 text-[10.5px] text-rose-300" role="alert">{draftError}</p> : null}
                      {editable ? (
                        <div className="mt-1.5 flex justify-end gap-1.5">
                          <button type="button" onClick={() => { setEditing(null); setDraftError(null); }} className="rounded px-2 py-1 text-[10.5px] text-muted-foreground hover:bg-accent hover:text-foreground">
                            Cancel
                          </button>
                          <button type="button" onClick={saveEdit} className="rounded bg-primary px-2.5 py-1 text-[10.5px] font-medium text-primary-foreground hover:bg-primary/90">
                            Save block
                          </button>
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              );
            })}
            {editable ? (
              <button
                type="button"
                onClick={addBlock}
                className="inline-flex items-center justify-center gap-1 rounded-md border border-dashed border-border/50 px-2 py-1.5 text-[11px] text-muted-foreground hover:border-primary/40 hover:text-foreground"
              >
                <Plus size={12} /> Add block
              </button>
            ) : null}
          </div>
        ) : mode === 'preview' ? (
          preview ? (
            <ResponseView response={preview} showActions={false} />
          ) : (
            <div className="flex items-start gap-2 p-2 text-xs text-rose-300">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>Preview unavailable — invalid JSON.</span>
            </div>
          )
        ) : (
          <div className="flex h-full min-h-[240px] flex-col gap-1">
            {mode === 'blocks' && !blocks ? (
              <p className="shrink-0 text-[10.5px] text-amber-300/90">
                Not a response envelope yet. Paste <code className="font-mono">{'{"blocks":[…]}'}</code> here.
              </p>
            ) : null}
            <textarea
              id="canvas-visual-source"
              aria-label="Envelope JSON"
              value={content}
              readOnly={!editable}
              spellCheck={false}
              onChange={(e) => onChange(e.target.value)}
              onSelect={handleSelect}
              onKeyUp={handleSelect}
              className="min-h-[220px] flex-1 resize-none rounded border border-border/40 bg-black/20 p-2.5 font-mono text-[11.5px] leading-relaxed text-foreground/90 outline-none focus:border-primary"
            />
          </div>
        )}
      </div>
    </div>
  );
}

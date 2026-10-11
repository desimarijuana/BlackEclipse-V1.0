'use client';

// ── ControlsBlock — backend-driven interactive parameters ─────────────────────
// Submitting composes a follow-up prompt from the (validated) control values and
// re-enters the EXISTING agent loop via `onFollowup`. No new backend contract and
// no privileged action: it is exactly as capable as the user typing the prompt.
// When there is no chat context (e.g. a detached render) the submit is disabled
// rather than pretending to work.

import { useState } from 'react';
import { Play } from '@/lib/icons';
import { cn } from '@/lib/utils';
import type { Control, ControlsBlock as ControlsBlockType } from '@/lib/response/contract';

type Value = string | number | { from: string; to: string };
type Values = Record<string, Value>;

function initialValues(controls: Control[]): Values {
  const out: Values = {};
  for (const c of controls) {
    switch (c.kind) {
      case 'select':
        out[c.id] = c.default ?? c.options[0]?.value ?? '';
        break;
      case 'date_range':
        out[c.id] = c.default ?? { from: '', to: '' };
        break;
      case 'slider':
        out[c.id] = c.default ?? c.min;
        break;
      case 'text':
        out[c.id] = c.default ?? '';
        break;
    }
  }
  return out;
}

function valueToString(value: Value): string {
  if (typeof value === 'object') return `${value.from || '?'}..${value.to || '?'}`;
  return String(value);
}

export function composePrompt(block: ControlsBlockType, values: Values): string {
  if (block.promptTemplate) {
    return block.promptTemplate.replace(/\{\{\s*([\w.]+)\s*\}\}/g, (_m, key: string) => {
      const [id, field] = key.split('.');
      const value = values[id];
      if (field && typeof value === 'object' && (field === 'from' || field === 'to')) return value[field] || '';
      if (value === undefined) return '';
      return valueToString(value);
    });
  }
  const parts = block.controls.map((c) => `${c.label}: ${valueToString(values[c.id])}`);
  const lead = block.description ?? block.title ?? 'Continue with these parameters';
  return `${lead} — ${parts.join('; ')}`;
}

export interface ControlsBlockProps {
  block: ControlsBlockType;
  onFollowup?: (prompt: string) => void;
}

export function ControlsBlock({ block, onFollowup }: ControlsBlockProps) {
  const [values, setValues] = useState<Values>(() => initialValues(block.controls));
  const [submitted, setSubmitted] = useState(false);
  const set = (id: string, value: Value) => setValues((v) => ({ ...v, [id]: value }));

  const submit = () => {
    if (!onFollowup) return;
    onFollowup(composePrompt(block, values));
    setSubmitted(true);
  };

  return (
    <div className="w-full rounded-xl border border-white/10 bg-accent/10 p-3">
      {block.title && <h4 className="mb-1 text-sm font-semibold text-foreground">{block.title}</h4>}
      {block.description && <p className="mb-2 text-[12px] text-muted-foreground">{block.description}</p>}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {block.controls.map((control) => {
          const value = values[control.id];
          const label = (
            <span className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-muted-foreground/70">
              {control.label}
            </span>
          );
          const inputCls =
            'w-full rounded-lg border border-border/60 bg-card/60 px-2 py-1.5 text-[13px] text-foreground outline-none focus:ring-1 focus:ring-primary';
          return (
            <label key={control.id} className="block">
              {label}
              {control.kind === 'select' && (
                <select
                  className={inputCls}
                  value={typeof value === 'string' ? value : ''}
                  onChange={(e) => set(control.id, e.target.value)}
                >
                  {control.options.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              )}
              {control.kind === 'date_range' && (
                <div className="flex items-center gap-2">
                  <input
                    type="date"
                    className={inputCls}
                    value={typeof value === 'object' ? value.from : ''}
                    onChange={(e) => set(control.id, { from: e.target.value, to: typeof value === 'object' ? value.to : '' })}
                  />
                  <span className="text-muted-foreground/50">–</span>
                  <input
                    type="date"
                    className={inputCls}
                    value={typeof value === 'object' ? value.to : ''}
                    onChange={(e) => set(control.id, { from: typeof value === 'object' ? value.from : '', to: e.target.value })}
                  />
                </div>
              )}
              {control.kind === 'slider' && (
                <div className="flex items-center gap-2">
                  <input
                    type="range"
                    className="flex-1 accent-primary"
                    min={control.min}
                    max={control.max}
                    step={control.step ?? 1}
                    value={typeof value === 'number' ? value : control.min}
                    onChange={(e) => set(control.id, Number(e.target.value))}
                  />
                  <span className="w-14 text-right text-[12px] tabular-nums text-foreground">{typeof value === 'number' ? value : control.min}</span>
                </div>
              )}
              {control.kind === 'text' && (
                <input
                  type="text"
                  className={inputCls}
                  placeholder={control.placeholder}
                  value={typeof value === 'string' ? value : ''}
                  onChange={(e) => set(control.id, e.target.value)}
                />
              )}
            </label>
          );
        })}
      </div>
      <div className="mt-3 flex items-center justify-between gap-2">
        <span className="text-[10px] text-muted-foreground/60">
          {onFollowup ? 'Runs a new agent turn with these parameters.' : 'Interactive run is unavailable here.'}
        </span>
        <button
          type="button"
          onClick={submit}
          disabled={!onFollowup}
          className={cn(
            'inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-[12px] font-medium text-primary-foreground transition-colors',
            !onFollowup ? 'cursor-not-allowed opacity-40' : 'hover:bg-primary/90',
          )}
        >
          <Play size={12} />
          {submitted ? 'Sent' : block.submitLabel ?? 'Run'}
        </button>
      </div>
    </div>
  );
}

export default ControlsBlock;

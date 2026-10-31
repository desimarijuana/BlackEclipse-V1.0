'use client';

// ── Config field ─────────────────────────────────────────────────────────────
// ONE renderer for a node config value, used by both the node card (`inline`)
// and the inspector (`panel`). Inline controls are compact Blender-style rows:
// a small label on the left and the widget on the right. The panel variant
// keeps the helper text and full-height controls. Editing is draft-based:
// text/number commit on blur or Enter, Escape reverts, booleans/selects commit
// immediately. `wired` disables the control when an incoming edge supplies it.

import { useEffect, useRef, useState, type ReactNode } from 'react';
import { cn } from '@/lib/utils';
import type { ConfigFieldDef } from '@/lib/graph-studio/types';

export interface ConfigFieldProps {
  field: ConfigFieldDef;
  value: unknown;
  variant: 'inline' | 'panel';
  wired?: boolean;
  disabled?: boolean;
  /** True when the current value differs from the node definition's default. */
  canReset?: boolean;
  onReset?: () => void;
  onCommit: (value: unknown) => void;
}

const BASE_INPUT =
  'w-full rounded-md border border-black/10 bg-background/60 px-2 text-foreground outline-none transition-colors placeholder:text-muted-foreground/60 focus:border-primary/50 dark:border-white/10';

const INLINE_INPUT =
  'nodrag nopan h-7 rounded-[5px] border border-black/10 bg-background/60 px-2 text-[10.5px] text-foreground outline-none transition-colors hover:border-black/20 hover:bg-background/75 focus:border-primary/50 focus:bg-background/70 dark:border-white/10 dark:hover:border-white/20';

function formatNumber(value: number, step: number): string {
  const decimals = step < 0.01 ? 3 : step < 0.1 ? 2 : step < 1 ? 1 : 0;
  return Number(value.toFixed(decimals)).toString();
}

/**
 * Blender-style number widget: drag horizontally to scrub, click (without
 * dragging) to type. Shift = fine, Ctrl/Cmd = coarse. The committed value is
 * clamped to the field's declared bounds.
 */
function DragNumber({
  field, value, disabled, onCommit,
}: {
  field: ConfigFieldDef;
  value: unknown;
  disabled?: boolean;
  onCommit: (value: unknown) => void;
}) {
  const step = field.step ?? (
    field.min != null && field.max != null && field.max - field.min <= 2 ? 0.01 : 1
  );
  const initial = value === undefined || value === null ? '' : String(value);
  const [text, setText] = useState(initial);
  const focused = useRef(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const drag = useRef<{ x: number; value: number; moved: boolean } | null>(null);

  useEffect(() => {
    if (!focused.current && !drag.current) setText(initial);
  }, [initial]);

  const clamp = (next: number): number => {
    let valueOut = next;
    if (field.min != null) valueOut = Math.max(field.min, valueOut);
    if (field.max != null) valueOut = Math.min(field.max, valueOut);
    if (step > 0) valueOut = Math.round(valueOut / step) * step;
    return valueOut;
  };

  const commit = (raw: string) => {
    const next = raw.trim() === '' ? 0 : Number(raw);
    if (!Number.isFinite(next)) {
      setText(initial);
      return;
    }
    const clamped = clamp(next);
    if (clamped !== Number(value)) onCommit(clamped);
    else setText(formatNumber(clamped, step));
  };

  return (
    <input
      ref={inputRef}
      type="text"
      inputMode="decimal"
      value={text}
      disabled={disabled}
      placeholder={field.placeholder}
      title="Drag to change · click to type"
      onChange={(event) => setText(event.target.value)}
      onFocus={() => { focused.current = true; }}
      onBlur={() => {
        focused.current = false;
        commit(text);
      }}
      onPointerDown={(event) => {
        if (disabled || event.button !== 0) return;
        event.preventDefault();
        event.stopPropagation();
        inputRef.current?.setPointerCapture(event.pointerId);
        drag.current = { x: event.clientX, value: Number(value) || 0, moved: false };
      }}
      onPointerMove={(event) => {
        const state = drag.current;
        if (!state) return;
        const dx = event.clientX - state.x;
        if (!state.moved && Math.abs(dx) < 3) return;
        state.moved = true;
        const factor = event.shiftKey ? 0.1 : event.ctrlKey || event.metaKey ? 10 : 1;
        const next = clamp(state.value + dx * step * factor);
        setText(formatNumber(next, step));
        onCommit(next);
      }}
      onPointerUp={(event) => {
        const state = drag.current;
        drag.current = null;
        if (state && !state.moved) {
          focused.current = true;
          inputRef.current?.focus();
          inputRef.current?.select();
        }
        if (inputRef.current?.hasPointerCapture(event.pointerId)) {
          inputRef.current.releasePointerCapture(event.pointerId);
        }
      }}
      onKeyDown={(event) => {
        if (event.key === 'Enter') {
          event.preventDefault();
          focused.current = false;
          commit(text);
          inputRef.current?.blur();
        } else if (event.key === 'Escape') {
          event.preventDefault();
          setText(initial);
          focused.current = false;
          inputRef.current?.blur();
        } else if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
          event.preventDefault();
          const direction = event.key === 'ArrowUp' ? 1 : -1;
          const factor = event.shiftKey ? 0.1 : event.ctrlKey || event.metaKey ? 10 : 1;
          const next = clamp((Number(value) || 0) + direction * step * factor);
          setText(formatNumber(next, step));
          onCommit(next);
        }
      }}
      className={cn(INLINE_INPUT, 'w-full tabular-nums')}
    />
  );
}

function JsonEditor({
  value, rows, onCommit,
}: {
  value: unknown;
  rows: number;
  onCommit: (value: unknown) => void;
}) {
  const serialized = JSON.stringify(value ?? null, null, 2);
  const [text, setText] = useState(serialized);
  const focused = useRef(false);
  useEffect(() => {
    if (!focused.current) setText(serialized);
  }, [serialized]);
  return (
    <textarea
      value={text}
      onChange={(event) => setText(event.target.value)}
      onFocus={() => { focused.current = true; }}
      onBlur={() => {
        focused.current = false;
        try {
          onCommit(JSON.parse(text));
        } catch {
          setText(serialized);
        }
      }}
      rows={rows}
      className={cn(BASE_INPUT, 'nodrag nowheel resize-y py-1.5 font-mono text-[11px]')}
    />
  );
}

/** Compact single-line JSON for the node card; full editing stays in the panel. */
function InlineJsonInput({
  value, disabled, onCommit,
}: {
  value: unknown;
  disabled?: boolean;
  onCommit: (value: unknown) => void;
}) {
  const serialized = JSON.stringify(value ?? null);
  const [text, setText] = useState(serialized);
  const focused = useRef(false);
  useEffect(() => {
    if (!focused.current) setText(serialized);
  }, [serialized]);
  return (
    <input
      type="text"
      value={text}
      disabled={disabled}
      spellCheck={false}
      placeholder="{}"
      onFocus={() => { focused.current = true; }}
      onChange={(event) => setText(event.target.value)}
      onBlur={() => {
        focused.current = false;
        try {
          onCommit(JSON.parse(text));
        } catch {
          setText(serialized);
        }
      }}
      onKeyDown={(event) => {
        if (event.key === 'Enter') {
          event.preventDefault();
          focused.current = false;
          (event.target as HTMLInputElement).blur();
        } else if (event.key === 'Escape') {
          event.preventDefault();
          setText(serialized);
          focused.current = false;
          (event.target as HTMLInputElement).blur();
        }
      }}
      className={cn(INLINE_INPUT, 'w-full font-mono text-[10px]')}
    />
  );
}

function InlineRow({ field, children }: { field: ConfigFieldDef; children: ReactNode }) {
  // Inline labels drop a trailing parenthetical ("Agent version (0 = latest)")
  // so the narrow card column stays readable; the tooltip keeps the full text.
  const shortLabel = field.label.replace(/\s*\(.*$/, '');
  return (
    <div className="flex h-8 items-center gap-2.5">
      <span
        className="w-[78px] shrink-0 truncate text-[9.5px] font-medium text-muted-foreground/85"
        title={field.help ?? field.label}
      >
        {shortLabel}
        {field.required && <span className="ml-0.5 text-rose-400">*</span>}
      </span>
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}

export function ConfigField({
  field, value, variant, wired = false, disabled = false, onCommit,
}: ConfigFieldProps) {
  const inline = variant === 'inline';
  const serialized = value === undefined || value === null ? '' : String(value);
  const [text, setText] = useState(serialized);
  const focused = useRef(false);

  useEffect(() => {
    if (!focused.current) setText(serialized);
  }, [serialized]);

  const commitDraft = (raw: string) => {
    if (field.kind === 'number') {
      const next = raw.trim() === '' ? 0 : Number(raw);
      if (!Number.isFinite(next)) {
        setText(serialized);
        return;
      }
      if (next !== Number(value)) onCommit(next);
      else setText(String(next));
      return;
    }
    if (raw !== serialized) onCommit(raw);
  };

  const panelLabel = (
    <>
      <span className="mb-1 block truncate text-[10.5px] text-muted-foreground" title={field.help}>
        {field.label}
        {field.required && <span className="ml-0.5 text-rose-400">*</span>}
      </span>
      {field.help && (
        <p className="mb-1 text-[10px] leading-snug text-muted-foreground/70">{field.help}</p>
      )}
    </>
  );

  const wrap = (control: ReactNode) => (
    inline
      ? <InlineRow field={field}>{control}</InlineRow>
      : <label className="block">{panelLabel}{control}</label>
  );

  if (wired) {
    return wrap(
      <span
        className={cn(
          'flex items-center gap-1 rounded-[5px] border border-dashed border-black/15 bg-black/[0.03] text-muted-foreground dark:border-white/15 dark:bg-white/[0.03]',
          inline ? 'h-7 px-2 text-[10px]' : 'px-2 py-1.5 text-[11px]',
        )}
        title="This value comes from the connected input wire."
      >
        <span className="h-1 w-1 rounded-full bg-primary" />
        From wire
      </span>,
    );
  }

  if (field.kind === 'json') {
    return wrap(
      inline
        ? <InlineJsonInput value={value} disabled={disabled} onCommit={onCommit} />
        : <JsonEditor value={value} rows={5} onCommit={onCommit} />,
    );
  }

  if (field.kind === 'boolean') {
    return wrap(
      <span className={cn('flex items-center gap-2', inline && 'h-6')}>
        <input
          type="checkbox"
          checked={Boolean(value)}
          disabled={disabled}
          onChange={(event) => onCommit(event.target.checked)}
          className={cn('nodrag accent-primary', inline ? 'h-3.5 w-3.5' : 'h-4 w-4')}
        />
        {!inline && (
          <span className="text-[11px] text-muted-foreground">
            {Boolean(value) ? 'Enabled' : 'Disabled'}
          </span>
        )}
      </span>,
    );
  }

  if (field.kind === 'select') {
    return wrap(
      <select
        value={serialized}
        disabled={disabled}
        onChange={(event) => onCommit(event.target.value)}
        className={cn(inline ? INLINE_INPUT : BASE_INPUT, inline ? 'w-full pr-1' : 'py-1.5 text-[12px]')}
      >
        {(field.options ?? []).map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
        {!field.options?.some((option) => option.value === serialized) && serialized !== '' && (
          <option value={serialized}>{serialized}</option>
        )}
      </select>,
    );
  }

  if (inline && field.kind === 'number') {
    return wrap(<DragNumber field={field} value={value} disabled={disabled} onCommit={onCommit} />);
  }

  return wrap(
    <input
      type={field.kind === 'number' ? 'number' : 'text'}
      inputMode={field.kind === 'number' ? 'decimal' : undefined}
      value={text}
      disabled={disabled}
      min={field.kind === 'number' ? field.min : undefined}
      max={field.kind === 'number' ? field.max : undefined}
      step={field.kind === 'number' ? field.step : undefined}
      placeholder={field.placeholder}
      onChange={(event) => setText(event.target.value)}
      onFocus={() => { focused.current = true; }}
      onBlur={() => {
        focused.current = false;
        commitDraft(text);
      }}
      onKeyDown={(event) => {
        if (event.key === 'Enter') {
          event.preventDefault();
          focused.current = false;
          commitDraft(text);
          (event.target as HTMLInputElement).blur();
        } else if (event.key === 'Escape') {
          event.preventDefault();
          setText(serialized);
          focused.current = false;
          (event.target as HTMLInputElement).blur();
        }
      }}
      className={cn(inline ? INLINE_INPUT : BASE_INPUT, inline ? 'w-full tabular-nums' : 'py-1.5 text-[12px]')}
    />,
  );
}

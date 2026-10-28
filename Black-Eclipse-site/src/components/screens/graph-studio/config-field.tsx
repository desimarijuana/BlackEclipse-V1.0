'use client';

// ── Config field ─────────────────────────────────────────────────────────────
// ONE renderer for a node config value, used by both the node card (`inline`)
// and the inspector (`panel`). Editing is draft-based: text/number commit on
// blur or Enter, Escape reverts, booleans/selects commit immediately. That keeps
// the node's IR-rebuild cycle from stealing focus or pushing one undo entry per
// keystroke. `wired` disables the control when an incoming edge supplies it.

import { useEffect, useRef, useState } from 'react';
import { cn } from '@/lib/utils';
import type { ConfigFieldDef } from '@/lib/graph-studio/types';

export interface ConfigFieldProps {
  field: ConfigFieldDef;
  value: unknown;
  variant: 'inline' | 'panel';
  wired?: boolean;
  disabled?: boolean;
  onCommit: (value: unknown) => void;
}

const BASE_INPUT =
  'w-full rounded-md border border-black/10 bg-background/60 px-2 text-foreground outline-none transition-colors placeholder:text-muted-foreground/60 focus:border-primary/50 dark:border-white/10';

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
      className={cn(BASE_INPUT, 'resize-y py-1.5 font-mono text-[11px]')}
    />
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

  const label = (
    <span
      className={cn(
        'block truncate text-muted-foreground',
        inline
          ? 'mb-0.5 text-[9px] font-medium uppercase tracking-[0.08em]'
          : 'mb-1 text-[10.5px]',
      )}
      title={field.help}
    >
      {field.label}
    </span>
  );

  if (wired) {
    return (
      <label className="block">
        {label}
        <span
          className={cn(
            'flex items-center gap-1 rounded-md border border-dashed border-black/10 text-muted-foreground dark:border-white/10',
            inline ? 'h-6 px-1.5 text-[10px]' : 'px-2 py-1.5 text-[11px]',
          )}
          title="This value comes from the connected input wire."
        >
          <span className="h-1 w-1 rounded-full bg-primary" />
          From wire
        </span>
      </label>
    );
  }

  if (field.kind === 'json') {
    return (
      <label className="block">
        {label}
        <JsonEditor value={value} rows={5} onCommit={onCommit} />
      </label>
    );
  }

  if (field.kind === 'boolean') {
    return (
      <label className={cn('block', !inline && 'flex flex-col')}>
        {label}
        <span className={cn('flex items-center gap-2', inline && 'h-6')}>
          <input
            type="checkbox"
            checked={Boolean(value)}
            disabled={disabled}
            onChange={(event) => onCommit(event.target.checked)}
            className={cn('accent-primary', inline ? 'h-3.5 w-3.5' : 'h-4 w-4')}
          />
          {!inline && (
            <span className="text-[11px] text-muted-foreground">
              {Boolean(value) ? 'Enabled' : 'Disabled'}
            </span>
          )}
        </span>
      </label>
    );
  }

  if (field.kind === 'select') {
    return (
      <label className="block">
        {label}
        <select
          value={serialized}
          disabled={disabled}
          onChange={(event) => onCommit(event.target.value)}
          className={cn(BASE_INPUT, inline ? 'h-6 text-[11px]' : 'py-1.5 text-[12px]')}
        >
          {(field.options ?? []).map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
          {!field.options?.some((option) => option.value === serialized) && serialized !== '' && (
            <option value={serialized}>{serialized}</option>
          )}
        </select>
      </label>
    );
  }

  return (
    <label className="block">
      {label}
      <input
        type={field.kind === 'number' ? 'number' : 'text'}
        inputMode={field.kind === 'number' ? 'decimal' : undefined}
        value={text}
        disabled={disabled}
        min={field.min}
        max={field.max}
        step={field.step}
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
        className={cn(BASE_INPUT, inline ? 'h-6 text-[11px] tabular-nums' : 'py-1.5 text-[12px]')}
      />
    </label>
  );
}

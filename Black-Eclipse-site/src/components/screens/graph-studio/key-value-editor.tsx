'use client';

// ── Key/value editor ─────────────────────────────────────────────────────────
// Structured editor for a record config value (data.set_variables). Each row
// keeps its own draft text so renaming a key does not fight React state, and
// commits emit a fresh plain object. Values keep their JSON type: string,
// number, boolean or a parsed JSON value.

import { useEffect, useRef, useState } from 'react';
import { Plus, Trash2 } from '@/lib/icons';
import { cn } from '@/lib/utils';

const CONTROL =
  'h-7 rounded-[5px] border border-white/10 bg-background/60 px-1.5 text-[10.5px] text-foreground outline-none focus:border-primary/50';

type RowType = 'string' | 'number' | 'boolean' | 'json';

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function typeOf(value: unknown): RowType {
  if (typeof value === 'number') return 'number';
  if (typeof value === 'boolean') return 'boolean';
  if (typeof value === 'string') return 'string';
  return 'json';
}

function uniqueKey(base: string, used: Set<string>): string {
  const cleaned = base.trim() || 'key';
  if (!used.has(cleaned)) return cleaned;
  let index = 2;
  while (used.has(`${cleaned}${index}`)) index += 1;
  return `${cleaned}${index}`;
}

function Row({
  name,
  value,
  onRename,
  onChange,
  onRemove,
}: {
  name: string;
  value: unknown;
  onRename: (next: string) => void;
  onChange: (next: unknown) => void;
  onRemove: () => void;
}) {
  const [draftName, setDraftName] = useState(name);
  const [jsonText, setJsonText] = useState(() => JSON.stringify(value ?? null));
  const [jsonError, setJsonError] = useState<string | null>(null);
  const nameFocused = useRef(false);
  const jsonFocused = useRef(false);

  useEffect(() => {
    if (!nameFocused.current) setDraftName(name);
  }, [name]);

  const kind = typeOf(value);

  const setKind = (next: RowType) => {
    if (next === kind) return;
    if (next === 'string') onChange(value == null ? '' : String(value));
    else if (next === 'number') onChange(Number(value) || 0);
    else if (next === 'boolean') onChange(Boolean(value));
    else {
      setJsonText(JSON.stringify(value ?? null, null, 2));
      onChange(value);
    }
  };

  return (
    <div className="flex items-start gap-1.5">
      <input
        value={draftName}
        spellCheck={false}
        onFocus={() => { nameFocused.current = true; }}
        onChange={(event) => setDraftName(event.target.value)}
        onBlur={() => {
          nameFocused.current = false;
          const next = draftName.trim();
          if (!next) setDraftName(name);
          else if (next !== name) onRename(next);
        }}
        placeholder="name"
        className={cn(CONTROL, 'w-[92px] shrink-0 font-mono')}
      />
      <select
        value={kind}
        onChange={(event) => setKind(event.target.value as RowType)}
        className={cn(CONTROL, 'w-[74px] shrink-0')}
        title="Value type"
      >
        <option value="string">string</option>
        <option value="number">number</option>
        <option value="boolean">boolean</option>
        <option value="json">JSON</option>
      </select>
      <div className="min-w-0 flex-1">
        {kind === 'boolean' ? (
          <label className="flex h-7 items-center gap-1.5 text-[10.5px] text-muted-foreground">
            <input
              type="checkbox"
              checked={Boolean(value)}
              onChange={(event) => onChange(event.target.checked)}
              className="h-3.5 w-3.5 accent-primary"
            />
            {Boolean(value) ? 'true' : 'false'}
          </label>
        ) : kind === 'json' ? (
          <>
            <input
              value={jsonText}
              spellCheck={false}
              placeholder="{}"
              onFocus={() => { jsonFocused.current = true; }}
              onChange={(event) => setJsonText(event.target.value)}
              onBlur={() => {
                jsonFocused.current = false;
                try {
                  onChange(JSON.parse(jsonText));
                  setJsonError(null);
                } catch {
                  setJsonError('invalid JSON');
                }
              }}
              className={cn(CONTROL, 'w-full font-mono')}
            />
            {jsonError && <span className="text-[9px] text-rose-300">{jsonError}</span>}
          </>
        ) : (
          <input
            value={value == null ? '' : String(value)}
            type={kind === 'number' ? 'number' : 'text'}
            onChange={(event) => {
              const raw = event.target.value;
              if (kind === 'number') onChange(raw.trim() === '' ? 0 : Number(raw));
              else onChange(raw);
            }}
            className={cn(CONTROL, 'w-full', kind === 'number' && 'tabular-nums')}
          />
        )}
      </div>
      <button
        type="button"
        onClick={onRemove}
        title="Remove variable"
        className="mt-0.5 shrink-0 rounded p-1 text-muted-foreground hover:text-rose-300"
      >
        <Trash2 size={11} />
      </button>
    </div>
  );
}

export function KeyValueEditor({
  value,
  onChange,
}: {
  value: unknown;
  onChange: (next: Record<string, unknown>) => void;
}) {
  const record = isRecord(value) ? value : {};
  const entries = Object.entries(record);

  const write = (next: Array<[string, unknown]>) => {
    onChange(Object.fromEntries(next));
  };

  const add = () => {
    const used = new Set(entries.map(([key]) => key));
    write([...entries, [uniqueKey('key', used), '']]);
  };

  return (
    <div className="space-y-1.5">
      {entries.length === 0 && (
        <p className="text-[10.5px] text-muted-foreground">No variables yet.</p>
      )}
      {entries.map(([key, entryValue]) => (
        <Row
          key={key}
          name={key}
          value={entryValue}
          onRename={(next) => {
            if (next !== key && Object.prototype.hasOwnProperty.call(record, next)) return;
            write(entries.map(([k, v]) => (k === key ? [next, v] : [k, v])));
          }}
          onChange={(next) => {
            write(entries.map(([k, v]) => (k === key ? [k, next] : [k, v])));
          }}
          onRemove={() => write(entries.filter(([k]) => k !== key))}
        />
      ))}
      <button
        type="button"
        onClick={add}
        className="flex items-center gap-1 rounded-md border border-white/10 bg-white/[0.03] px-2 py-1 text-[10px] text-muted-foreground hover:text-foreground"
      >
        <Plus size={10} /> Add variable
      </button>
    </div>
  );
}

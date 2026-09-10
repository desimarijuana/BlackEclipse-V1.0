'use client';

// ── WidgetConfigPanel — per-instance widget configuration ───────────────────
// Reusable across any customizable workspace. Takes a `getDefinition` resolver
// so it never imports a specific registry. Renders the config fields declared
// by a WidgetDefinition and saves them to the widget instance's `config`.

import React, { useState } from 'react';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { WidgetConfigField, WidgetDefinition } from '@/lib/workspace/widget-def';
import type { WidgetPlacement } from '@/lib/workspace/types';

export function WidgetConfigPanel({
  placement,
  getDefinition,
  onSave,
  onClose,
}: {
  placement: WidgetPlacement;
  getDefinition: (id: string) => WidgetDefinition | undefined;
  onSave: (patch: Record<string, unknown>) => void;
  onClose: () => void;
}) {
  const def = getDefinition(placement.widgetId);
  const fields = def?.configFields ?? [];
  const [values, setValues] = useState<Record<string, unknown>>(() => ({
    ...(def?.defaultConfig ?? {}),
    ...(placement.config ?? {}),
  }));

  const set = (key: string, value: unknown) => setValues(prev => ({ ...prev, [key]: value }));

  return (
    <div className="fixed inset-0 z-40 flex justify-end animate-fade-in" data-nodrag>
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />
      <aside className="relative flex w-80 max-w-[85vw] flex-col h-full border-l border-white/15 dark:border-white/10 glass-card-strong shadow-2xl shadow-black/40 animate-slide-in">
        <div className="flex items-center justify-between px-4 py-3 border-b border-border/10">
          <span className="font-serif text-sm font-semibold text-foreground">Configure · {def?.label ?? placement.widgetId}</span>
          <button onClick={onClose} className="rounded-lg p-1 text-muted-foreground hover:text-foreground hover:bg-accent cursor-pointer">
            <X size={14} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto scrollbar-hide p-4">
          {fields.length === 0 ? (
            <p className="text-xs text-muted-foreground/70 italic">This widget has no configurable settings yet.</p>
          ) : (
            <div className="flex flex-col gap-4">
              {fields.map(f => <Field key={f.key} field={f} value={values[f.key]} onChange={v => set(f.key, v)} />)}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-border/10 px-4 py-3">
          <button
            onClick={() => onSave(values)}
            className="rounded-xl border border-primary/40 bg-primary/15 text-primary px-4 py-2 text-xs font-bold hover:bg-primary/25 transition-all cursor-pointer"
          >
            Save
          </button>
        </div>
      </aside>
    </div>
  );
}

function Field({ field, value, onChange }: { field: WidgetConfigField; value: unknown; onChange: (v: unknown) => void }) {
  const inputCls = 'w-full bg-background/60 border border-border/40 hover:border-primary/50 rounded-xl px-2.5 py-1.5 text-xs font-mono focus:ring-1 focus:ring-primary outline-none';
  const labelCls = 'text-[9px] uppercase tracking-widest font-bold text-muted-foreground';

  switch (field.type) {
    case 'text':
      return (
        <label className="flex flex-col gap-1">
          <span className={labelCls}>{field.label}</span>
          <input
            type="text"
            value={String(value ?? '')}
            placeholder={field.placeholder}
            onChange={e => onChange(e.target.value)}
            className={inputCls}
          />
        </label>
      );
    case 'number':
      return (
        <label className="flex flex-col gap-1">
          <span className={labelCls}>{field.label}</span>
          <input
            type="number"
            value={Number(value ?? field.default ?? 0)}
            min={field.min}
            max={field.max}
            step={field.step}
            onChange={e => onChange(Number(e.target.value))}
            className={inputCls}
          />
        </label>
      );
    case 'select':
      return (
        <label className="flex flex-col gap-1">
          <span className={labelCls}>{field.label}</span>
          <select
            value={String(value ?? '')}
            onChange={e => onChange(e.target.value)}
            className={cn(inputCls, 'appearance-none')}
          >
            {field.options?.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </label>
      );
    case 'boolean':
      return (
        <label className="flex items-center justify-between gap-2 cursor-pointer">
          <span className={labelCls}>{field.label}</span>
          <input
            type="checkbox"
            checked={Boolean(value)}
            onChange={e => onChange(e.target.checked)}
            className="h-4 w-4 accent-primary cursor-pointer"
          />
        </label>
      );
    default:
      return null;
  }
}

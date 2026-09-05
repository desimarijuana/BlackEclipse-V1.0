'use client';

// ── Shared customization UI primitives (v2 — section model) ─────────────────
// StructurePicker: Elementor-style column-structure popover for a section.
// SectionShell: hover-outlined section frame with a floating toolbar
// (structure picker + delete). WidthPicker remains for in-section slot width.
// TemplateMiniGrid: preset preview. These are the single source of these
// visuals — screens must not hand-roll their own.

import { useState, useRef, useEffect } from 'react';
import { Columns3, GripVertical, Trash2, X, MoveHorizontal } from 'lucide-react';

export const SPAN_CLASS: Record<1 | 2 | 3 | 4, string> = {
  1: 'lg:col-span-1',
  2: 'lg:col-span-2',
  3: 'lg:col-span-3',
  4: 'lg:col-span-4',
};

export const SPAN_TITLE: Record<1 | 2 | 3 | 4, string> = {
  1: 'Small — quarter of the row',
  2: 'Medium — half of the row',
  3: 'Large — three quarters of the row',
  4: 'Full — entire row width',
};

/** Visual "width" picker — each option is a mini bar of 1–4 blocks. */
export function WidthPicker({
  value,
  onChange,
  compact,
}: {
  value: 1 | 2 | 3 | 4;
  onChange: (s: 1 | 2 | 3 | 4) => void;
  compact?: boolean;
}) {
  return (
    <div
      className={`inline-flex items-center rounded-full border border-border/40 bg-accent/30 backdrop-blur-sm ${compact ? 'gap-1 px-1 py-0.5' : 'gap-1.5 px-2 py-1'} shrink-0`}
      role="group"
      aria-label="Widget width"
    >
      <MoveHorizontal
        className={`${compact ? 'w-3 h-3' : 'w-3.5 h-3.5'} text-muted-foreground/70 shrink-0`}
        aria-hidden
      />
      <div className="flex items-center gap-0.5">
        {([1, 2, 3, 4] as const).map((s) => {
          const active = value === s;
          return (
            <button
              key={s}
              onClick={(e) => { e.stopPropagation(); onChange(s); }}
              title={SPAN_TITLE[s]}
              aria-label={SPAN_TITLE[s]}
              aria-pressed={active}
              className={`${compact ? 'h-[20px] px-1' : 'h-[26px] px-1.5'} rounded-full cursor-pointer transition-all duration-150 ${
                active
                  ? 'bg-primary/15 ring-1 ring-primary/50'
                  : 'hover:bg-foreground/[0.06]'
              }`}
            >
              <span className={`flex ${compact ? 'gap-[1.5px]' : 'gap-[2px]'} items-end`} aria-hidden>
                {[1, 2, 3, 4].map((b) => (
                  <span
                    key={b}
                    className={`${compact ? 'w-[2.5px]' : 'w-[3px]'} rounded-full transition-colors duration-150 ${
                      active
                        ? b <= s
                          ? 'bg-primary'
                          : 'bg-primary/20'
                        : b <= s
                          ? 'bg-muted-foreground/50'
                          : 'bg-muted-foreground/15'
                    }`}
                    style={{ height: b <= s ? (b === s ? (compact ? 9 : 12) : compact ? 7 : 10) : compact ? 3 : 4 }}
                  />
                ))}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

/** Column structures offered by the StructurePicker (Elementor-style). */
export const STRUCTURE_PRESETS: Array<{ columns: 1 | 2 | 3 | 4; label: string; cells: number[] }> = [
  { columns: 1, label: 'Single — full width', cells: [1] },
  { columns: 2, label: 'Two columns — 50 / 50', cells: [1, 1] },
  { columns: 3, label: 'Three columns — 33 / 33 / 33', cells: [1, 1, 1] },
  { columns: 4, label: 'Four columns — 25 × 4', cells: [1, 1, 1, 1] },
];

function StructureIcon({ cells, active }: { cells: number[]; active: boolean }) {
  return (
    <span className={`flex gap-[2px] w-8 h-5 p-[2px] rounded-[4px] border ${active ? 'border-primary/60 bg-primary/10' : 'border-border/50 bg-background/40'}`} aria-hidden>
      {cells.map((_, i) => (
        <span key={i} className={`flex-1 rounded-[2px] ${active ? 'bg-primary' : 'bg-muted-foreground/40'}`} />
      ))}
    </span>
  );
}

/** Popover to choose a section's column structure. */
export function StructurePicker({
  columns,
  onPick,
  align = 'right',
}: {
  columns: 1 | 2 | 3 | 4;
  onPick: (c: 1 | 2 | 3 | 4) => void;
  align?: 'left' | 'right';
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);
  return (
    <div ref={ref} className="relative">
      <button
        onClick={(e) => { e.stopPropagation(); setOpen((v) => !v); }}
        title="Section columns"
        className="p-1.5 rounded-md text-zinc-200 hover:bg-zinc-500/20 cursor-pointer transition-colors"
      >
        <Columns3 className="w-3.5 h-3.5" />
      </button>
      {open && (
        <div
          onClick={(e) => e.stopPropagation()}
          className={`absolute top-[calc(100%+6px)] ${align === 'right' ? 'right-0' : 'left-0'} z-50 w-56 rounded-xl border border-border/50 bg-[#101010]/97 backdrop-blur-md shadow-xl shadow-black/40 p-1.5 animate-fade-in-up`}
        >
          <p className="text-[9px] uppercase font-bold tracking-wider text-muted-foreground px-2 py-1">Section columns</p>
          {STRUCTURE_PRESETS.map((p) => (
            <button
              key={p.columns}
              onClick={(e) => { e.stopPropagation(); onPick(p.columns); setOpen(false); }}
              className={`w-full flex items-center gap-2.5 px-2 py-1.5 rounded-lg text-[11px] font-semibold cursor-pointer transition-colors ${
                columns === p.columns ? 'text-primary bg-primary/10' : 'text-zinc-200 hover:bg-zinc-500/15'
              }`}
            >
              <StructureIcon cells={p.cells} active={columns === p.columns} />
              {p.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}


/** Section frame shown while customizing: hover outline + floating toolbar. */
export function SectionShell({
  editing,
  columns,
  onColumns,
  onDelete,
  empty,
  children,
}: {
  editing: boolean;
  columns: 1 | 2 | 3 | 4;
  onColumns: (c: 1 | 2 | 3 | 4) => void;
  onDelete: () => void;
  empty?: boolean;
  children: React.ReactNode;
}) {
  if (!editing) return <>{children}</>;
  return (
    <div
      className={`relative group/section rounded-2xl transition-all duration-150 ${
        empty ? 'border border-dashed border-zinc-400/40 p-4' : 'ring-1 ring-transparent hover:ring-zinc-400/40 p-0'
      }`}
    >
      {children}
      {/* Floating section toolbar */}
      <div className="absolute -top-3 right-3 z-30 hidden group-hover/section:flex items-center gap-0.5 rounded-full bg-zinc-800/95 backdrop-blur-md border border-white/20 shadow-lg px-1.5 py-1">
        <span className="text-[8.5px] font-mono font-bold text-zinc-400 tracking-wider uppercase px-1.5 select-none">Section</span>
        <StructurePicker columns={columns} onPick={onColumns} />
        <button
          onClick={(e) => { e.stopPropagation(); onDelete(); }}
          title="Delete empty section"
          className="p-1.5 rounded-md text-zinc-400 hover:text-rose-400 hover:bg-zinc-500/20 cursor-pointer transition-colors"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>
      {empty && (
        <p className="text-[10px] text-muted-foreground/70 text-center mt-1 select-none">Empty section — drop a widget here</p>
      )}
    </div>
  );
}

/** Mini column diagram for a preset row (used in Navigator). */
export function SectionChips({ widgets, editing }: { widgets: Array<{ id: string; visible: boolean }>; editing?: boolean }) {
  if (!editing) return null;
  return (
    <span className="flex items-center gap-1 text-[9px] font-mono text-muted-foreground/70">
      <GripVertical className="w-3 h-3" />
      {widgets.map((w) => w.id).join(' · ')}
      {widgets.some((w) => !w.visible) && <X className="w-3 h-3 text-rose-400/70" />}
    </span>
  );
}
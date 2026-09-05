'use client';

// ── Shared customization UI primitives (v3 — Section → Column → Element) ────
// StructurePicker: column-count popover for a section.
// SectionShell: section frame (hover outline + toolbar: columns, spacing, delete).
// ColumnShell: column frame (hover outline + width picker).
// ElementShell: per-element frame (name chip + toolbar: width, height, padding,
// align, hide). Element styling is fully separate from column/layout styling.

import { useState, useRef, useEffect, type ReactNode, type CSSProperties } from 'react';
import {
  Columns3, GripVertical, Trash2, MoveHorizontal, Maximize2, Settings2, AlignLeft,
  AlignCenter, AlignRight, AlignJustify, Eye, EyeOff,
} from 'lucide-react';
import type { ElementStyle, Section } from './types';

export const SPAN_CLASS: Record<1 | 2 | 3 | 4, string> = {
  1: 'lg:col-span-1',
  2: 'lg:col-span-2',
  3: 'lg:col-span-3',
  4: 'lg:col-span-4',
};

// ── StructurePicker (column count for a section) ────────────────────────────
export const STRUCTURE_PRESETS: Array<{ columns: 1 | 2 | 3 | 4; label: string; cells: number[] }> = [
  { columns: 1, label: 'One column', cells: [1] },
  { columns: 2, label: 'Two columns', cells: [1, 1] },
  { columns: 3, label: 'Three columns', cells: [1, 1, 1] },
  { columns: 4, label: 'Four columns', cells: [1, 1, 1, 1] },
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

export function Popover({ label, children, align = 'right' }: { label: ReactNode; children: (close: () => void) => ReactNode; align?: 'left' | 'right' }) {
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
        className="p-1.5 rounded-md text-zinc-200 hover:bg-zinc-500/20 cursor-pointer transition-colors"
      >
        {label}
      </button>
      {open && (
        <div
          onClick={(e) => e.stopPropagation()}
          className={`absolute top-[calc(100%+6px)] ${align === 'right' ? 'right-0' : 'left-0'} z-50 w-60 rounded-xl border border-border/50 bg-[#101010]/97 backdrop-blur-md shadow-xl shadow-black/40 p-1.5 animate-fade-in-up`}
        >
          {children(() => setOpen(false))}
        </div>
      )}
    </div>
  );
}

export function StructurePicker({ columns, onPick }: { columns: 1 | 2 | 3 | 4; onPick: (c: 1 | 2 | 3 | 4) => void }) {
  return (
    <Popover label={<Columns3 className="w-3.5 h-3.5" />}>
      {(close) => (
        <>
          <p className="text-[9px] uppercase font-bold tracking-wider text-muted-foreground px-2 py-1">Section columns</p>
          {STRUCTURE_PRESETS.map((p) => (
            <button
              key={p.columns}
              onClick={(e) => { e.stopPropagation(); onPick(p.columns); close(); }}
              className={`w-full flex items-center gap-2.5 px-2 py-1.5 rounded-lg text-[11px] font-semibold cursor-pointer transition-colors ${
                columns === p.columns ? 'text-primary bg-primary/10' : 'text-zinc-200 hover:bg-zinc-500/15'
              }`}
            >
              <StructureIcon cells={p.cells} active={columns === p.columns} />
              {p.label}
            </button>
          ))}
        </>
      )}
    </Popover>
  );
}

// ── Section spacing controls ────────────────────────────────────────────────
export function SectionSpacingPicker({ gap, padding, onChange }: { gap: Section['gap']; padding: Section['padding']; onChange: (p: { gap?: Section['gap']; padding?: Section['padding'] }) => void }) {
  return (
    <Popover label={<Maximize2 className="w-3.5 h-3.5" />}>
      {(close) => (
        <>
          <p className="text-[9px] uppercase font-bold tracking-wider text-muted-foreground px-2 py-1">Section spacing</p>
          <div className="px-2 py-1">
            <p className="text-[10px] font-bold text-zinc-300 mb-1">Column gap</p>
            <div className="flex gap-1">
              {([0, 8, 16, 24] as const).map((g) => (
                <button
                  key={g}
                  onClick={(e) => { e.stopPropagation(); onChange({ gap: g }); close(); }}
                  className={`flex-1 py-1 rounded-md text-[10px] font-bold cursor-pointer border transition-colors ${
                    gap === g ? 'bg-primary/15 text-primary border-primary/50' : 'text-zinc-300 border-border/40 hover:bg-zinc-500/15'
                  }`}
                >
                  {g}px
                </button>
              ))}
            </div>
            <p className="text-[10px] font-bold text-zinc-300 mt-2 mb-1">Padding</p>
            <div className="flex gap-1">
              {(['none', 'sm', 'md'] as const).map((p) => (
                <button
                  key={p}
                  onClick={(e) => { e.stopPropagation(); onChange({ padding: p }); close(); }}
                  className={`flex-1 py-1 rounded-md text-[10px] font-bold capitalize cursor-pointer border transition-colors ${
                    padding === p ? 'bg-primary/15 text-primary border-primary/50' : 'text-zinc-300 border-border/40 hover:bg-zinc-500/15'
                  }`}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>
        </>
      )}
    </Popover>
  );
}

// ── Column width picker (relative share) ────────────────────────────────────
export function ColumnWidthPicker({ width, onPick }: { width: 1 | 2 | 3 | 4; onPick: (w: 1 | 2 | 3 | 4) => void }) {
  return (
    <Popover label={<><MoveHorizontal className="w-3.5 h-3.5" /></>}>
      {(close) => (
        <>
          <p className="text-[9px] uppercase font-bold tracking-wider text-muted-foreground px-2 py-1">Column width</p>
          {([1, 2, 3, 4] as const).map((w) => (
            <button
              key={w}
              onClick={(e) => { e.stopPropagation(); onPick(w); close(); }}
              className={`w-full flex items-center gap-2.5 px-2 py-1.5 rounded-lg text-[11px] font-semibold cursor-pointer transition-colors ${
                width === w ? 'text-primary bg-primary/10' : 'text-zinc-200 hover:bg-zinc-500/15'
              }`}
            >
              <StructureIcon cells={Array.from({ length: w }, () => 1)} active={width === w} />
              {'Narrow Wide Stretch Full'.split(' ')[w - 1]} (×{w})
            </button>
          ))}
        </>
      )}
    </Popover>
  );
}

// ── Element style controls (per-element, separate from layout) ──────────────
export function ElementStylePicker({
  style,
  onChange,
}: {
  style: ElementStyle;
  onChange: (p: Partial<ElementStyle>) => void;
}) {
  return (
    <Popover label={<Settings2 className="w-3.5 h-3.5" />}>
      {(close) => (
        <div className="space-y-2 px-2 py-1">
          <p className="text-[9px] uppercase font-bold tracking-wider text-muted-foreground">Element style</p>
          <div>
            <p className="text-[10px] font-bold text-zinc-300 mb-1">Width in column</p>
            <div className="flex gap-1">
              {(['auto', 1, 2, 3, 4] as const).map((w) => (
                <button
                  key={String(w)}
                  onClick={(e) => { e.stopPropagation(); onChange({ width: w }); }}
                  className={`flex-1 py-1 rounded-md text-[10px] font-bold cursor-pointer border transition-colors ${
                    style.width === w ? 'bg-primary/15 text-primary border-primary/50' : 'text-zinc-300 border-border/40 hover:bg-zinc-500/15'
                  }`}
                >
                  {w === 'auto' ? 'Fill' : `${w * 25}%`}
                </button>
              ))}
            </div>
          </div>
          <div>
            <p className="text-[10px] font-bold text-zinc-300 mb-1">Min height</p>
            <div className="flex items-center gap-1">
              <button
                onClick={(e) => { e.stopPropagation(); onChange({ height: Math.max(0, style.height - 1) }); }}
                className="flex-1 py-1 rounded-md text-[10px] font-bold cursor-pointer border border-border/40 text-zinc-300 hover:bg-zinc-500/15"
              >
                −
              </button>
              <span className="text-[10px] font-mono text-zinc-300 w-10 text-center">{style.height * 40}px</span>
              <button
                onClick={(e) => { e.stopPropagation(); onChange({ height: Math.min(10, style.height + 1) }); }}
                className="flex-1 py-1 rounded-md text-[10px] font-bold cursor-pointer border border-border/40 text-zinc-300 hover:bg-zinc-500/15"
              >
                +
              </button>
            </div>
          </div>
          <div>
            <p className="text-[10px] font-bold text-zinc-300 mb-1">Inner padding</p>
            <div className="flex gap-1">
              {(['none', 'sm', 'md'] as const).map((p) => (
                <button
                  key={p}
                  onClick={(e) => { e.stopPropagation(); onChange({ padding: p }); }}
                  className={`flex-1 py-1 rounded-md text-[10px] font-bold capitalize cursor-pointer border transition-colors ${
                    style.padding === p ? 'bg-primary/15 text-primary border-primary/50' : 'text-zinc-300 border-border/40 hover:bg-zinc-500/15'
                  }`}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>
          <div>
            <p className="text-[10px] font-bold text-zinc-300 mb-1">Alignment</p>
            <div className="flex gap-1">
              {([
                ['stretch', AlignJustify], ['start', AlignLeft], ['center', AlignCenter], ['end', AlignRight],
              ] as const).map(([a, Icon]) => (
                <button
                  key={a}
                  onClick={(e) => { e.stopPropagation(); onChange({ align: a }); }}
                  className={`flex-1 py-1 rounded-md cursor-pointer border transition-colors flex items-center justify-center ${
                    style.align === a ? 'bg-primary/15 text-primary border-primary/50' : 'text-zinc-300 border-border/40 hover:bg-zinc-500/15'
                  }`}
                  title={a}
                >
                  <Icon className="w-3.5 h-3.5" />
                </button>
              ))}
            </div>
          </div>
          <button
            onClick={(e) => { e.stopPropagation(); close(); }}
            className="w-full py-1.5 rounded-md text-[10px] font-bold uppercase tracking-wider text-primary bg-primary/10 hover:bg-primary/20 cursor-pointer"
          >
            Done
          </button>
        </div>
      )}
    </Popover>
  );
}

// ── Shells ──────────────────────────────────────────────────────────────────
const HANDLE = 'bg-zinc-800/90 backdrop-blur-md border border-white/20 shadow-lg';

export const SECTION_GAP_CLASS: Record<Section['gap'], string> = {
  0: 'gap-0',
  8: 'gap-2',
  16: 'gap-4',
  24: 'gap-6',
};

export const SECTION_PAD_CLASS: Record<Section['padding'], string> = {
  none: 'p-0',
  sm: 'p-2',
  md: 'p-4',
};

export const ELEM_PAD_CLASS: Record<ElementStyle['padding'], string> = {
  none: 'p-0',
  sm: 'p-2',
  md: 'p-4',
};

export const ELEM_ALIGN_CLASS: Record<ElementStyle['align'], string> = {
  stretch: 'self-stretch',
  start: 'self-start',
  center: 'self-center',
  end: 'self-end',
};

/** Inline flex-grow style from a column's width share. */
export function columnFlexStyle(width: 1 | 2 | 3 | 4): CSSProperties {
  return { flexGrow: width, flexBasis: 0, minWidth: 0 };
}

/** Section frame shown while customizing. */
export function SectionShell({
  editing,
  gap,
  padding,
  onSpacing,
  onColumns,
  columns,
  onDelete,
  children,
}: {
  editing: boolean;
  gap: Section['gap'];
  padding: Section['padding'];
  onSpacing: (p: { gap?: Section['gap']; padding?: Section['padding'] }) => void;
  onColumns: (c: 1 | 2 | 3 | 4) => void;
  columns: number;
  onDelete: () => void;
  children: ReactNode;
}) {
  if (!editing) return <div className={SECTION_PAD_CLASS[padding]}>{children}</div>;
  return (
    <div className="relative group/section rounded-2xl ring-1 ring-transparent hover:ring-zinc-400/40 transition-all duration-150">
      {children}
      <div className="absolute -top-3 right-3 z-30 flex items-center gap-0.5 rounded-full bg-zinc-800/95 backdrop-blur-md border border-white/20 shadow-lg px-1.5 py-1 opacity-0 pointer-events-none group-hover/section:opacity-100 group-hover/section:pointer-events-auto transition-opacity duration-150">
        <span className="text-[8.5px] font-mono font-bold text-zinc-400 tracking-wider uppercase px-1.5 select-none">Section · {columns} col</span>
        <StructurePicker columns={Math.min(4, columns) as 1 | 2 | 3 | 4} onPick={onColumns} />
        <SectionSpacingPicker gap={gap} padding={padding} onChange={onSpacing} />
        <button
          onClick={(e) => { e.stopPropagation(); onDelete(); }}
          title="Hide all elements in this section"
          className="p-1.5 rounded-md text-zinc-400 hover:text-rose-400 hover:bg-zinc-500/20 cursor-pointer transition-colors"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}

/** Column frame shown while customizing: hover outline + width control. */
export function ColumnShell({
  editing,
  width,
  onWidth,
  elementCount,
  children,
  onDropInColumn,
  dragging,
}: {
  editing: boolean;
  width: 1 | 2 | 3 | 4;
  onWidth: (w: 1 | 2 | 3 | 4) => void;
  elementCount: number;
  children: ReactNode;
  onDropInColumn: () => void;
  dragging: boolean;
}) {
  const [over, setOver] = useState(false);
  if (!editing) return <>{children}</>;
  return (
    <div
      className={`relative group/column min-w-0 rounded-xl transition-all duration-150 ${
        dragging && over ? 'ring-2 ring-primary/60 bg-primary/[0.04]' : 'ring-1 ring-transparent hover:ring-zinc-400/30'
      }`}
      onDragOver={(e) => { if (dragging) { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; setOver(true); } }}
      onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setOver(false); }}
      onDrop={(e) => { if (dragging) { e.preventDefault(); setOver(false); onDropInColumn(); } }}
    >
      {children}
      <div className="absolute -top-2.5 right-2 z-30 flex items-center opacity-0 pointer-events-none group-hover/column:opacity-100 group-hover/column:pointer-events-auto transition-opacity duration-150 gap-0.5 rounded-full bg-zinc-800/95 backdrop-blur-md border border-white/20 shadow-md px-1 py-0.5">
        <span className="text-[8px] font-mono font-bold text-zinc-500 uppercase px-1 select-none">Col · {elementCount}</span>
        <ColumnWidthPicker width={width} onPick={onWidth} />
      </div>
 {elementCount === 0 && (
        <div className="min-h-[80px] rounded-lg border border-dashed border-zinc-500/40 flex items-center justify-center">
          <span className="text-[10px] text-muted-foreground/60 select-none">Drop element here</span>
        </div>
      )}
    </div>
  );
}

/** Per-element frame: name chip + style toolbar + hide. Pure presentation. */
export function ElementShell({
  editing,
  label,
  style,
  onStyle,
  visible,
  onToggleVisible,
  dragging,
  dragOver,
  children,
  onDragStart,
  onDragEnd,
  onDragOverElement,
  onDropOnElement,
}: {
  editing: boolean;
  label: string;
  style: ElementStyle;
  onStyle: (p: Partial<ElementStyle>) => void;
  visible: boolean;
  onToggleVisible: () => void;
  dragging: boolean;
  dragOver: boolean;
  children: ReactNode;
  onDragStart: (e: React.DragEvent) => void;
  onDragEnd: () => void;
  onDragOverElement: (e: React.DragEvent) => void;
  onDropOnElement: (e: React.DragEvent) => void;
}) {
  if (!editing) {
    return (
      <div className={ELEM_ALIGN_CLASS[style.align]} style={{ width: style.width === 'auto' ? undefined : `${style.width * 25}%`, minHeight: style.height > 0 ? style.height * 40 : undefined }}>
        {children}
      </div>
    );
  }
  return (
    <div
      draggable
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onDragOver={onDragOverElement}
      onDrop={onDropOnElement}
      className={`relative group/elem rounded-xl transition-all duration-150 ${dragging ? 'opacity-50 scale-[0.98]' : ''} ${
        dragOver ? 'ring-2 ring-primary/70 ring-offset-2 ring-offset-transparent' : 'ring-1 ring-transparent hover:ring-zinc-400/40'
      } cursor-grab active:cursor-grabbing`}
    >
      {children}
      {/* Name chip + toolbar */}
      <div className={`absolute -top-2.5 left-2 z-30 flex items-center opacity-0 pointer-events-none group-hover/elem:opacity-100 group-hover/elem:pointer-events-auto transition-opacity duration-150 gap-0.5 rounded-full ${HANDLE} px-1.5 py-0.5`}>
        <GripVertical className="w-3 h-3 text-zinc-300 cursor-grab" />
        <span className="text-[8.5px] font-mono font-bold text-zinc-100 tracking-wider uppercase max-w-[110px] truncate select-none">{label}</span>
        <ElementStylePicker style={style} onChange={onStyle} />
        <button
          onClick={(e) => { e.stopPropagation(); onToggleVisible(); }}
          title={visible ? 'Hide element' : 'Show element'}
          className="p-1 rounded-md text-zinc-300 hover:bg-zinc-500/20 cursor-pointer transition-colors"
        >
          {visible ? <Eye className="w-3 h-3" /> : <EyeOff className="w-3 h-3" />}
        </button>
      </div>
      {!visible && <div className="absolute inset-0 rounded-xl bg-[#0b0b0b]/60 border border-dashed border-zinc-500/40 pointer-events-none" />}
    </div>
  );
}

/** Preset preview: one bar per visual row; hidden widgets render dashed. */
export function TemplateMiniGrid({ rows }: { rows: Array<{ span: number; hidden?: boolean }> }) {
  return (
    <div className="flex flex-col gap-1" aria-hidden>
      {rows.map((r, i) => (
        r.hidden ? (
          <div key={i} className="h-1.5 rounded-full border border-dashed border-border/50 w-1/3" />
        ) : (
          <div key={i} className="flex gap-1" style={{ width: `${(r.span / 4) * 100}%` }}>
            <div className="h-1.5 rounded-full bg-primary/40 flex-1" />
          </div>
        )
      ))}
    </div>
  );
}
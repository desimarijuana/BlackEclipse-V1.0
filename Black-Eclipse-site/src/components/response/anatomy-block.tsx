'use client';

// ── AnatomyBlock — interactive isometric mechanism figure ─────────────────────
//
// Renders a declarative `anatomy` block with the Anatomy-derived isometric
// geometry (`lib/anatomy/scene.ts` compiles the scene; `lib/anatomy/iso-kit.ts`
// supplies the math). The drawing is deliberately SELF-CONTAINED: every path is
// painted with explicit `fill`/`stroke` SVG presentation attributes and an inline
// palette, with NO dependency on the kit's stylesheet. That removes the whole
// class of "the CSS did not load, so `var()` is undefined and everything paints
// black" failures — the figure renders correctly even with zero CSS applied.
//
// The look is a graphite sketch on dark paper: near-black solid fills with thin
// grey ink outlines, muted accent lines for flow, and light-grey labels.

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { ChevronLeft, ChevronRight, Maximize2, Pause, Play, RotateCcw, X } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { useDarkScheme } from '@/hooks/use-dark-scheme';
import { useStillness } from '@/lib/anatomy/live';
import type { AnatomyBlock as AnatomyBlockType } from '@/lib/response/contract';
import { compileAnatomy, type CompiledAnatomy } from '@/lib/anatomy/scene';
import { pathOf, type SolidPaths } from '@/lib/anatomy/iso-kit';

const AUTOPLAY_MS = 2400;
const MONO = 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';
const STROKE = 0.7;

export interface AnatomyBlockProps {
  block: AnatomyBlockType;
  className?: string;
}

// ── Palette (explicit, not CSS variables) ─────────────────────────────────────

interface Palette {
  /** The "paper" panel behind the figure. */
  panel: string;
  /** Solid body fill and its top/shade gradients. */
  paper: string;
  top: string;
  shades: [string, string, string, string];
  litTop: string;
  litShade: string;
  face: string;
  /** Ink (line) ramp. */
  ink: { hi: string; mid: string; lo: string; faint: string };
  /** Accent ink for lit/flow lines. */
  accent: { lit: string; red: string; green: string; blue: string; warning: string };
  text: string;
  halo: string;
  dot: string;
  border: string;
}

const DARK: Palette = {
  panel: '#101012',
  paper: '#141416',
  top: '#303032',
  shades: ['#0f0f11', '#18181a', '#242426', '#303032'],
  litTop: '#3a3a3d',
  litShade: '#2c2c2e',
  face: '#1b1b1d',
  ink: { hi: '#e6e9ec', mid: '#b4bbc1', lo: '#90969c', faint: '#646b71' },
  accent: { lit: '#f2f5f7', red: '#e58383', green: '#7fd7a6', blue: '#8bb0f2', warning: '#e6c069' },
  text: '#cfd4d9',
  halo: '#000000',
  dot: '#c9ced3',
  border: 'rgba(255,255,255,0.07)',
};

const LIGHT: Palette = {
  panel: '#eef0f1',
  paper: '#e4e7e9',
  top: '#ffffff',
  shades: ['#d8dbde', '#dfe2e4', '#e6e8ea', '#eef0f1'],
  litTop: '#ffffff',
  litShade: '#eef1f2',
  face: '#ffffff',
  ink: { hi: '#26292d', mid: '#565c62', lo: '#8b9198', faint: '#b7bcc2' },
  accent: { lit: '#0e1013', red: '#bd4636', green: '#2f8a5b', blue: '#3b6fd4', warning: '#a9791f' },
  text: '#3a3f45',
  halo: '#9aa0a5',
  dot: '#3a3f44',
  border: 'rgba(0,0,0,0.08)',
};

function lineColor(p: Palette, tone: string): string {
  switch (tone) {
    case 'info': return p.accent.blue;
    case 'success': return p.accent.green;
    case 'warning': return p.accent.warning;
    case 'danger': return p.accent.red;
    default: return p.ink.mid;
  }
}

/** A stage's `lit` is a boolean (all/none) or an explicit id list. */
function stageLitIds(lit: boolean | string[] | undefined, allIds: string[]): Set<string> {
  if (lit === true) return new Set(allIds);
  if (Array.isArray(lit)) return new Set(lit);
  return new Set();
}

function dashOf(dotted: boolean, dashed: boolean, flow: boolean): string | undefined {
  if (dotted) return '0.6 3';
  if (dashed) return '3 3';
  if (flow) return '2 6';
  return undefined;
}

// ── The self-contained SVG renderer ───────────────────────────────────────────

function SolidShape({ paths, lit, halo, palette }: {
  paths: SolidPaths;
  lit: boolean;
  halo: boolean;
  palette: Palette;
}) {
  // Neutral grey ink for the construct itself; tone colour is reserved for the
  // wires/legend so the solids read as the base/highlight greys (pencil on paper).
  const edge = lit ? palette.ink.hi : palette.ink.mid;
  const creaseInk = lit ? palette.ink.hi : palette.ink.faint;
  return (
    <g>
      {halo && (
        <path d={paths.fill} fill={palette.halo} opacity={0.5} style={{ filter: 'blur(9px)' }} transform="translate(0 3)" />
      )}
      <path d={paths.fill} fill={lit ? palette.face : palette.paper} />
      {lit
        ? <path d={paths.shades.filter(Boolean).join('')} fill={palette.litShade} />
        : paths.shades.map((d, i) => (d ? <path key={i} d={d} fill={palette.shades[i] ?? palette.shades[3]} /> : null))}
      <path d={paths.top} fill={lit ? palette.litTop : palette.top} />
      {paths.crease && <path d={paths.crease} fill="none" stroke={creaseInk} strokeWidth={STROKE * 0.7} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />}
      {paths.bevel && <path d={paths.bevel} fill="none" stroke={creaseInk} strokeWidth={STROKE * 0.7} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />}
      <path d={paths.outline} fill="none" stroke={edge} strokeWidth={STROKE} vectorEffect="non-scaling-stroke" strokeLinejoin="round" strokeLinecap="round" />
    </g>
  );
}

function IsoScene({ scene, litIds, palette, ariaLabel, maxHeight, labelIndex }: {
  scene: CompiledAnatomy;
  litIds: Set<string>;
  palette: Palette;
  ariaLabel: string;
  maxHeight?: string;
  labelIndex: Map<string, number>;
}) {
  const r = Math.max(7, Math.min(14, Math.round(scene.viewBox.h * 0.02)));
  return (
    <svg
      viewBox={`${scene.viewBox.x} ${scene.viewBox.y} ${scene.viewBox.w} ${scene.viewBox.h}`}
      role="img"
      aria-label={ariaLabel}
      preserveAspectRatio="xMidYMid meet"
      style={{ display: 'block', width: '100%', height: 'auto', maxHeight, overflow: 'visible' }}
    >
      {/* wires first so solids sit on top */}
      {scene.wires.map((wire, i) => {
        const d = pathOf([wire.from, ...wire.via, wire.to]);
        const stroke = lineColor(palette, wire.tone);
        return (
          <g key={`w-${i}`} fill="none" stroke={stroke} strokeWidth={STROKE} vectorEffect="non-scaling-stroke" strokeLinejoin="round" strokeLinecap="round">
            <path d={d} strokeDasharray={dashOf(wire.dotted, wire.dashed, wire.flow)} />
            <circle cx={Math.round(wire.from[0] * 10) / 10} cy={Math.round(wire.from[1] * 10) / 10} r={1.3} fill={palette.paper} strokeWidth={STROKE} vectorEffect="non-scaling-stroke" />
            <circle cx={Math.round(wire.to[0] * 10) / 10} cy={Math.round(wire.to[1] * 10) / 10} r={1.3} fill={palette.paper} strokeWidth={STROKE} vectorEffect="non-scaling-stroke" />
          </g>
        );
      })}
      {/* parts, painted in depth order (compiler preserves scene order) */}
      {scene.parts.map((part) => {
        const lit = part.lit || litIds.has(part.id);
        const n = labelIndex.get(part.id);
        return (
          <g key={part.id}>
            <SolidShape paths={part.paths} lit={lit} halo={part.halo || lit} palette={palette} />
            {part.overlay && (
              <path d={part.overlay} fill="none" stroke={palette.ink.faint} strokeWidth={STROKE * 0.8} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
            )}
            {part.overlayStrong && (
              <path d={part.overlayStrong} fill="none" stroke={palette.ink.lo} strokeWidth={STROKE} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
            )}
            {part.dots?.map((p, i) => (
              <circle key={`d${i}`} cx={p[0]} cy={p[1]} r={1.1} fill={palette.ink.lo} />
            ))}
            {/* Numbered callout — the long label lives in the key below the
                figure (SVG text cannot wrap, so in-plane labels overflowed). */}
            {n !== undefined && (
              <g>
                <circle cx={part.anchor[0]} cy={part.anchor[1]} r={r} fill={palette.panel} stroke={palette.ink.lo} strokeWidth={1.2} vectorEffect="non-scaling-stroke" />
                <text x={part.anchor[0]} y={part.anchor[1]} fontSize={r * 1.35} fontFamily={MONO} fontWeight={600} fill={palette.text} textAnchor="middle" dominantBaseline="central">
                  {n}
                </text>
              </g>
            )}
          </g>
        );
      })}
    </svg>
  );
}

// ── Legend / controls ─────────────────────────────────────────────────────────

function LegendChip({ mark, label, palette }: { mark?: string; label: string; palette: Palette }) {
  const m = (mark ?? '').toLowerCase();
  const stroke = m.includes('red') ? palette.accent.red
    : m.includes('green') ? palette.accent.green
      : m.includes('blue') ? palette.accent.blue
        : (m.includes('warn') || m.includes('amber')) ? palette.accent.warning
          : (m.includes('muted') || m.includes('dim') || m.includes('faint')) ? palette.ink.lo
            : palette.ink.mid;
  const dash = m.includes('dotted') ? '0.4 3' : m.includes('dashed') ? '3 2.5' : undefined;
  const solid = /cyl|solid|raised|flat|lit|box|disc|slab/.test(m);
  const faded = /dim|faint|muted/.test(m);
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground">
      <svg width={15} height={10} viewBox="0 0 15 10" aria-hidden="true" className="shrink-0" opacity={faded ? 0.6 : 1}>
        <path
          d={solid ? 'M2 5 7.5 2 13 5 7.5 8Z' : 'M1.5 5h12'}
          fill="none"
          stroke={stroke}
          strokeWidth={1.1}
          strokeDasharray={dash}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      </svg>
      {label}
    </span>
  );
}

function StageButton({ label, onClick, children }: { label: string; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-border/40 bg-accent/25 text-foreground/80 transition-colors hover:bg-accent/50 hover:text-foreground"
    >
      {children}
    </button>
  );
}

function FullPageButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title="View figure full page"
      aria-label="View figure full page"
      className="inline-flex items-center gap-1 whitespace-nowrap rounded-full border border-border/50 bg-accent/30 px-2.5 py-1 text-[11px] text-muted-foreground transition-colors hover:bg-accent/60 hover:text-foreground"
    >
      <Maximize2 size={12} /> Full page
    </button>
  );
}

function FigureBody({
  block,
  scene,
  litIds,
  palette,
  readout,
  describedBy,
  onFullPage,
  controls,
  large,
  maxHeight,
}: {
  block: AnatomyBlockType;
  scene: CompiledAnatomy;
  litIds: Set<string>;
  palette: Palette;
  readout: string;
  describedBy: string;
  onFullPage?: () => void;
  controls?: ReactNode;
  large?: boolean;
  maxHeight?: string;
}) {
  const labeled = scene.parts.filter((p) => p.label && p.label.trim());
  const labelIndex = new Map(labeled.map((p, i) => [p.id, i + 1]));

  return (
    <>
      <div className="mb-3 grid grid-cols-[1fr_auto_1fr] items-center gap-2 border-b border-border/40 pb-3">
        <span className="truncate font-mono text-[10px] uppercase tracking-widest text-muted-foreground/60">
          {block.fig ?? 'Fig.'}
        </span>
        <div className="min-w-0 text-center">
          {block.title && (
            <h3 className={cn('break-words font-semibold tracking-tight text-foreground', large ? 'text-lg' : 'text-base')} title={block.title}>
              {block.title}
            </h3>
          )}
          {block.hint && <p className="mt-0.5 text-[11px] text-muted-foreground">{block.hint}</p>}
        </div>
        <div className="justify-self-end">{onFullPage && <FullPageButton onClick={onFullPage} />}</div>
      </div>

      <div className="rounded-lg p-3 sm:p-4" style={{ background: palette.panel, border: `1px solid ${palette.border}` }}>
        {scene.parts.length === 0 ? (
          <p className="py-10 text-center text-[12px] text-muted-foreground">No parts in this figure.</p>
        ) : (
          <IsoScene scene={scene} litIds={litIds} palette={palette} ariaLabel={block.description ?? 'Isometric figure'} maxHeight={maxHeight} labelIndex={labelIndex} />
        )}
      </div>

      {labeled.length > 0 && (
        <ol className="mt-3 space-y-1.5">
          {labeled.map((p, i) => (
            <li key={p.id} className="flex gap-2 text-[12px] leading-snug">
              <span className="mt-px inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full border border-border/50 font-mono text-[10px] font-semibold text-foreground/80">
                {i + 1}
              </span>
              <span className="text-muted-foreground">{p.label}</span>
            </li>
          ))}
        </ol>
      )}

      {(block.legend.length > 0 || readout) && (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
            {block.legend.map((key, i) => (
              <LegendChip key={i} mark={key.mark} label={key.label} palette={palette} />
            ))}
          </div>
          {readout && <span className="font-mono text-[11px] tabular-nums text-muted-foreground">{readout}</span>}
        </div>
      )}

      {controls}

      {block.caption && <p className="mt-2 text-[11px] leading-snug text-muted-foreground/80">{block.caption}</p>}

      <p id={describedBy} className="sr-only">
        {block.description ?? `Isometric figure with ${scene.parts.length} parts and ${scene.wires.length} connections.`}
      </p>

      {scene.diagnostics.length > 0 && (
        <p className="mt-1 text-[11px] text-amber-400/80">{scene.diagnostics.join(' ')}</p>
      )}
    </>
  );
}

function AnatomyViewer({
  block,
  scene,
  litIds,
  palette,
  readout,
  controls,
  onClose,
}: {
  block: AnatomyBlockType;
  scene: CompiledAnatomy;
  litIds: Set<string>;
  palette: Palette;
  readout: string;
  controls: ReactNode;
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = previous;
    };
  }, [onClose]);

  const overlay = (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center"
      role="dialog"
      aria-modal="true"
      aria-label={block.title ? `${block.title} (full page)` : 'Figure (full page)'}
    >
      <button aria-label="Close full page figure" onClick={onClose} className="absolute inset-0 cursor-pointer bg-black/70 backdrop-blur-md" />
      <div className="glass-card-strong relative z-10 flex h-[90vh] w-[94vw] max-w-6xl flex-col overflow-hidden rounded-2xl border border-white/10">
        <div className="flex shrink-0 items-center justify-between gap-2 border-b border-white/10 px-4 py-2.5">
          <span className="truncate font-mono text-[10px] uppercase tracking-widest text-muted-foreground/70">
            {block.title ? `${block.title} · full page` : 'Figure · full page'}
          </span>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-lg p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <X size={16} />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-auto p-6">
          <FigureBody
            block={{ ...block, fig: undefined, title: undefined, hint: undefined }}
            scene={scene}
            litIds={litIds}
            palette={palette}
            readout={readout}
            describedBy="anatomy-full-alt"
            controls={controls}
            large
            maxHeight="none"
          />
        </div>
      </div>
    </div>
  );

  return typeof document !== 'undefined' ? createPortal(overlay, document.body) : null;
}

export function AnatomyBlock({ block, className }: AnatomyBlockProps) {
  const scene = useMemo(() => {
    try {
      return compileAnatomy(block);
    } catch {
      return null;
    }
  }, [block]);

  const dark = useDarkScheme(true);
  const palette = dark ? DARK : LIGHT;
  const stages = block.stages;
  const [stageIndex, setStageIndex] = useState(0);
  const [playing, setPlaying] = useState(block.animate === true);
  const [full, setFull] = useState(false);
  const still = useStillness();
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const currentStage = stageIndex > 0 ? stages[stageIndex - 1] : undefined;
  const hasStages = stages.length > 0;
  const readout = currentStage?.readout ?? block.readout ?? '';

  useEffect(() => {
    const shouldPlay = playing && hasStages && !still;
    if (!shouldPlay) {
      if (timer.current) clearInterval(timer.current);
      timer.current = null;
      return;
    }
    timer.current = setInterval(() => {
      setStageIndex((prev) => (prev + 1) % (stages.length + 1));
    }, AUTOPLAY_MS);
    return () => {
      if (timer.current) clearInterval(timer.current);
      timer.current = null;
    };
  }, [playing, hasStages, still, stages.length]);

  const openFull = useCallback(() => setFull(true), []);
  const closeFull = useCallback(() => setFull(false), []);

  if (!scene) {
    return <p className={cn('text-[12px] text-muted-foreground/80', className)}>This figure could not be compiled.</p>;
  }

  const litIds = stageLitIds(currentStage?.lit, scene.parts.map((p) => p.id));
  const describedBy = `anatomy-alt-${block.id ?? 'anon'}`;

  const controls = hasStages ? (
    <div className="mt-3 flex flex-wrap items-center gap-2">
      <div className="flex items-center gap-1">
        <StageButton label="Previous stage" onClick={() => { setPlaying(false); setStageIndex((p) => (p <= 0 ? stages.length : p - 1)); }}>
          <ChevronLeft className="h-3.5 w-3.5" />
        </StageButton>
        <StageButton label={playing ? 'Pause' : 'Play'} onClick={() => setPlaying((p) => !p)}>
          {playing ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
        </StageButton>
        <StageButton label="Next stage" onClick={() => { setPlaying(false); setStageIndex((p) => (p >= stages.length ? 0 : p + 1)); }}>
          <ChevronRight className="h-3.5 w-3.5" />
        </StageButton>
        <StageButton label="Reset" onClick={() => { setPlaying(false); setStageIndex(0); }}>
          <RotateCcw className="h-3.5 w-3.5" />
        </StageButton>
      </div>
      <span className="text-[11px] text-muted-foreground">
        {currentStage ? (
          <>
            <span className="font-medium text-foreground">{currentStage.label}</span>
            {currentStage.note ? ` — ${currentStage.note}` : ''}
          </>
        ) : (
          `${stages.length} stage${stages.length === 1 ? '' : 's'}`
        )}
      </span>
    </div>
  ) : null;

  return (
    <>
      <div className={cn('be-anatomy glass-card mx-auto w-full max-w-4xl rounded-xl p-4 sm:p-5', className)}>
        <FigureBody
          block={block}
          scene={scene}
          litIds={litIds}
          palette={palette}
          readout={readout}
          describedBy={describedBy}
          onFullPage={openFull}
          controls={controls}
          maxHeight="min(72vh,620px)"
        />
      </div>
      {full && (
        <AnatomyViewer
          block={block}
          scene={scene}
          litIds={litIds}
          palette={palette}
          readout={readout}
          controls={controls}
          onClose={closeFull}
        />
      )}
    </>
  );
}

export default AnatomyBlock;

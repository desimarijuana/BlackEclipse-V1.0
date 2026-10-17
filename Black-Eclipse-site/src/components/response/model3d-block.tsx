'use client';

// ── Model3dBlock — an interactive, orbitable 3D model ─────────────────────────
//
// Renders a declarative `model3d` block. The scene is compiled purely by
// `lib/model3d/compile.ts`; the WebGL viewport is loaded lazily (ssr:false) so
// `ogl` never enters the initial chat bundle and never runs during SSR/tests.
// The numbered key, legend, readout and stages live in the DOM, so the figure
// stays readable and accessible even if WebGL is unavailable.

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import dynamic from 'next/dynamic';
import { createPortal } from 'react-dom';
import { ChevronLeft, ChevronRight, Download, Maximize2, Pause, Play, RotateCcw, X } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { useStillness } from '@/lib/anatomy/live';
import type { Model3dBlock as Model3dBlockType } from '@/lib/response/contract';
import { compileModel3d, model3dStats, type CompiledModel3d } from '@/lib/model3d/compile';
import { buildGlb } from '@/lib/model3d/glb';

const Model3dCanvas = dynamic(() => import('./model3d-canvas').then((m) => m.Model3dCanvas), {
  ssr: false,
  loading: () => (
    <div className="flex h-full w-full items-center justify-center">
      <span className="h-6 w-6 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-primary" />
    </div>
  ),
});

const AUTOPLAY_MS = 2600;

export interface Model3dBlockProps {
  block: Model3dBlockType;
  className?: string;
}

function stageLitIds(lit: boolean | string[] | undefined, all: string[]): Set<string> {
  if (lit === true) return new Set(all);
  if (Array.isArray(lit)) return new Set(lit);
  return new Set();
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

function LegendChip({ mark, label }: { mark?: string; label: string }) {
  const m = (mark ?? '').toLowerCase();
  const dot = m.includes('red') ? 'bg-red-400'
    : m.includes('green') ? 'bg-emerald-400'
      : m.includes('blue') ? 'bg-blue-400'
        : (m.includes('warn') || m.includes('amber')) ? 'bg-amber-400'
          : m.includes('metal') ? 'bg-zinc-300'
            : 'bg-zinc-400';
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground">
      <span className={cn('inline-block h-2.5 w-2.5 shrink-0 rounded-sm', dot)} />
      {label}
    </span>
  );
}

function downloadScene(scene: CompiledModel3d, name: string): void {
  const bytes = buildGlb(scene.parts);
  const blob = new Blob([bytes.buffer as ArrayBuffer], { type: 'model/gltf-binary' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `${name.replace(/[^a-z0-9-_]+/gi, '-').slice(0, 60) || 'eclipse-model'}.glb`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

interface BodyProps {
  block: Model3dBlockType;
  scene: CompiledModel3d;
  litIds: Set<string>;
  still: boolean;
  error: string | null;
  readout: string;
  onError: (message: string) => void;
  onFull?: () => void;
  large?: boolean;
  height: number;
}

function Model3dBody({ block, scene, litIds, still, error, readout, onError, onFull, large, height }: BodyProps) {
  const stats = model3dStats(scene);
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
        <div className="flex items-center justify-self-end gap-1.5">
          {onFull && (
            <button
              type="button"
              onClick={onFull}
              title="View full page"
              aria-label="View full page"
              className="inline-flex items-center gap-1 whitespace-nowrap rounded-full border border-border/50 bg-accent/30 px-2.5 py-1 text-[11px] text-muted-foreground transition-colors hover:bg-accent/60 hover:text-foreground"
            >
              <Maximize2 size={12} /> Full page
            </button>
          )}
        </div>
      </div>

      <div
        className="relative overflow-hidden rounded-lg border border-white/10 bg-[#0b0b0d]"
        style={{ height }}
        role="img"
        aria-label={block.description ?? `3D model with ${stats.parts} parts`}
      >
        {error ? (
          <div className="flex h-full items-center justify-center px-6 text-center text-[12px] text-muted-foreground">
            {error}
          </div>
        ) : scene.parts.length === 0 ? (
          <div className="flex h-full items-center justify-center text-[12px] text-muted-foreground">
            No parts in this model.
          </div>
        ) : (
          <Model3dCanvas scene={scene} litGroups={litIds} still={still} autoRotate={block.animate === true} onError={onError} />
        )}
        {!error && scene.parts.length > 0 && (
          <span className="pointer-events-none absolute bottom-2 right-3 font-mono text-[10px] text-white/35">
            drag to orbit · scroll to zoom
          </span>
        )}
      </div>

      {scene.keys.length > 0 && (
        <ol className="mt-3 space-y-1.5">
          {scene.keys.map((key, i) => (
            <li key={key.id} className="flex gap-2 text-[12px] leading-snug">
              <span className="mt-px inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full border border-border/50 font-mono text-[10px] font-semibold text-foreground/80">
                {i + 1}
              </span>
              <span className="text-muted-foreground">{key.label}</span>
            </li>
          ))}
        </ol>
      )}

      {(block.legend.length > 0 || readout) && (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
            {block.legend.map((key, i) => (
              <LegendChip key={i} mark={key.mark} label={key.label} />
            ))}
          </div>
          {readout && <span className="font-mono text-[11px] tabular-nums text-muted-foreground">{readout}</span>}
        </div>
      )}

      {block.caption && <p className="mt-2 text-[11px] leading-snug text-muted-foreground/80">{block.caption}</p>}

      {scene.diagnostics.length > 0 && (
        <p className="mt-1 text-[11px] text-amber-400/80">{scene.diagnostics.join(' ')}</p>
      )}
    </>
  );
}

export function Model3dBlock({ block, className }: Model3dBlockProps) {
  const scene = useMemo(() => {
    try {
      return compileModel3d(block);
    } catch {
      return null;
    }
  }, [block]);

  const [stageIndex, setStageIndex] = useState(0);
  const [playing, setPlaying] = useState(block.animate === true);
  const [full, setFull] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const still = useStillness();
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const stages = block.stages;

  const currentStage = stageIndex > 0 ? stages[stageIndex - 1] : undefined;
  const hasStages = stages.length > 0;

  useEffect(() => {
    const shouldPlay = playing && hasStages && !still;
    if (!shouldPlay) {
      if (timer.current) clearInterval(timer.current);
      timer.current = null;
      return;
    }
    timer.current = setInterval(() => setStageIndex((prev) => (prev + 1) % (stages.length + 1)), AUTOPLAY_MS);
    return () => {
      if (timer.current) clearInterval(timer.current);
      timer.current = null;
    };
  }, [playing, hasStages, still, stages.length]);

  const openFull = useCallback(() => setFull(true), []);
  const closeFull = useCallback(() => setFull(false), []);

  if (!scene) {
    return <p className={cn('text-[12px] text-muted-foreground/80', className)}>This model could not be compiled.</p>;
  }

  const litIds = stageLitIds(currentStage?.lit, scene.keys.map((k) => k.id));
  const readout = currentStage?.readout ?? block.readout ?? '';

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

  const viewer = full && typeof document !== 'undefined'
    ? createPortal(
        <div className="fixed inset-0 z-[100] flex items-center justify-center" role="dialog" aria-modal="true" aria-label="3D model (full page)">
          <button aria-label="Close full page model" onClick={closeFull} className="absolute inset-0 cursor-pointer bg-black/70 backdrop-blur-md" />
          <div className="glass-card-strong relative z-10 flex h-[92vh] w-[94vw] max-w-6xl flex-col overflow-hidden rounded-2xl border border-white/10">
            <div className="flex shrink-0 items-center justify-between gap-2 border-b border-white/10 px-4 py-2.5">
              <span className="truncate font-mono text-[10px] uppercase tracking-widest text-muted-foreground/70">
                {block.title ? `${block.title} · full page` : 'Model · full page'}
              </span>
              <button type="button" onClick={closeFull} aria-label="Close" className="rounded-lg p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground">
                <X size={16} />
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-auto p-5">
              <Model3dBody block={{ ...block, fig: undefined, title: undefined, hint: undefined }} scene={scene} litIds={litIds} still={still} error={error} readout={readout} onError={setError} large height={560} />
              {controls}
            </div>
          </div>
        </div>,
        document.body,
      )
    : null;

  return (
    <>
      <div className={cn('be-model3d glass-card mx-auto w-full max-w-4xl rounded-xl p-4 sm:p-5', className)}>
        <Model3dBody
          block={block}
          scene={scene}
          litIds={litIds}
          still={still}
          error={error}
          readout={readout}
          onError={setError}
          onFull={openFull}
          height={Math.min(560, block.height)}
        />
        {controls}
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => downloadScene(scene, block.title ?? 'eclipse-model')}
            className="inline-flex items-center gap-1.5 rounded-full border border-border/50 bg-accent/30 px-3 py-1 text-[11px] text-muted-foreground transition-colors hover:bg-accent/60 hover:text-foreground"
          >
            <Download size={12} /> Download .glb
          </button>
          <span className="font-mono text-[10px] text-muted-foreground/60">
            {model3dStats(scene).parts} parts · {model3dStats(scene).triangles} tris
          </span>
        </div>
      </div>
      {viewer}
    </>
  );
}

export default Model3dBlock;

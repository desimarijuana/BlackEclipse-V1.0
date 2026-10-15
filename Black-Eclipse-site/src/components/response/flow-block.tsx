'use client';

// ── FlowBlock — dependency-free HTML/CSS process flow ──────────────────────────
// Renders an ordered process as cards joined by CSS connectors: each step is a
// card, and a step may branch into parallel `paths` rendered as smaller cards.
// No SVG, no diagram library — plain flex/grid so it reflows on narrow screens
// and inherits the app's frosted-glass theme. Read-only; renders validated data
// only. Distinct from `workflow` (strictly linear icon stages) and `diagram`
// (an absolute-positioned SVG node/edge graph).
//
// Layout: the card is CENTERED and width-capped (not full width) and its steps
// are centered. Icons render WHITE and uncoloured — tone/status no longer tints
// the glyph (status stays readable via the small status dot/check by the label).
// A visible "Full page" control opens the WHOLE FLOW in a full-screen overlay,
// larger, over the blurred page (the background behind it stays visible).

import { Fragment, useCallback, useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { ArrowRight, Check, Maximize2, X, type LucideIcon } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { resolveResponseIcon } from '@/lib/response/icons';
import type { FlowBlock as FlowBlockType, FlowPath, FlowStep } from '@/lib/response/contract';

function StatusGlyph({ status }: { status?: FlowPath['status'] }) {
  if (!status) return null;
  if (status === 'done') return <Check size={12} className="shrink-0 text-emerald-300" aria-hidden="true" />;
  return (
    <span
      aria-hidden="true"
      className={cn(
        'h-1.5 w-1.5 shrink-0 rounded-full',
        status === 'active' && 'bg-sky-400',
        status === 'error' && 'bg-rose-400',
        status === 'pending' && 'bg-muted-foreground/50',
      )}
    />
  );
}

/** The semantic icon, rendered white and uncoloured (no tone/status tint). */
function IconGlyph({ icon, size, box }: { icon?: string; size: number; box: string }) {
  const Icon: LucideIcon = resolveResponseIcon(icon);
  return (
    <span className={cn('flex shrink-0 items-center justify-center rounded-lg bg-accent/30 text-white ring-1 ring-border/50', box)}>
      <Icon size={size} strokeWidth={1.6} className="text-white" aria-hidden="true" />
    </span>
  );
}

function Connector({ horizontal, large }: { horizontal: boolean; large?: boolean }) {
  return (
    <li
      aria-hidden="true"
      className={cn(
        'flex shrink-0 items-center justify-center text-muted-foreground/40',
        horizontal ? 'py-0.5 sm:px-0.5 sm:py-0' : 'py-1',
      )}
    >
      <ArrowRight size={large ? 18 : 14} className={cn('rotate-90', horizontal && 'sm:rotate-0')} />
    </li>
  );
}

function PathCard({ path, large }: { path: FlowPath; large?: boolean }) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-border/40 bg-accent/[0.14] px-2.5 py-1.5 text-left">
      <IconGlyph icon={path.icon} size={large ? 15 : 12} box={large ? 'h-8 w-8' : 'h-6 w-6'} />
      <div className="min-w-0 flex-1">
        <p className={cn('flex items-center gap-1.5 font-medium text-foreground', large ? 'text-[13px]' : 'text-[12px]')}>
          <span className="truncate" title={path.label}>
            {path.label}
          </span>
          <StatusGlyph status={path.status} />
        </p>
        {path.description && (
          <p className={cn('mt-0.5 leading-snug text-muted-foreground/85', large ? 'text-[12px]' : 'text-[11px]')}>
            {path.description}
          </p>
        )}
      </div>
    </div>
  );
}

function StepColumn({ step, large }: { step: FlowStep; large?: boolean }) {
  return (
    <li className={cn('w-full min-w-0 sm:w-auto', large ? 'sm:max-w-[20rem]' : 'sm:max-w-[16rem]')}>
      <div className={cn('glass-card-subtle flex w-full flex-col items-center rounded-xl text-center', large ? 'gap-3 px-7 py-6' : 'gap-2.5 px-5 py-4')}>
        <IconGlyph icon={step.icon} size={large ? 28 : 20} box={large ? 'h-14 w-14' : 'h-10 w-10'} />
        <p className={cn('font-medium text-foreground', large ? 'text-[15px]' : 'text-[13px]')} title={step.label}>
          {step.label}
        </p>
        {step.description && (
          <p className={cn('leading-snug text-muted-foreground/85', large ? 'text-[13px]' : 'text-[11.5px]')}>
            {step.description}
          </p>
        )}
      </div>
      {step.paths.length > 0 && (
        <ul className="mt-2 flex flex-col gap-1.5">
          {step.paths.map((path, i) => (
            <li key={path.id ?? i}>
              <PathCard path={path} large={large} />
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

function FlowSteps({ block, large }: { block: FlowBlockType; large?: boolean }) {
  const horizontal = block.direction === 'LR';
  return (
    <ol className={cn('flex items-center justify-center', large ? 'gap-2.5' : 'gap-2', horizontal ? 'flex-col sm:flex-row sm:items-start sm:gap-3' : 'flex-col')}>
      {block.steps.map((step, i) => (
        <Fragment key={step.id ?? i}>
          {i > 0 && <Connector horizontal={horizontal} large={large} />}
          <StepColumn step={step} large={large} />
        </Fragment>
      ))}
    </ol>
  );
}

/**
 * Full-screen view of the WHOLE flow. Portaled to `document.body` for the same
 * containing-block reason as the app's other overlays: a transformed/filtered
 * chat ancestor scopes `position: fixed` and traps it, which is what made the
 * overlay overlap page elements. As a portal it covers the true viewport, over a
 * blurred page backdrop, with the card inset from the edges.
 */
function FlowViewer({ block, onClose }: { block: FlowBlockType; onClose: () => void }) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    // Lock page scroll while open (mirrors the app's other overlays).
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = previous;
    };
  }, [onClose]);

  const overlay = (
    <div className="fixed inset-0 z-[100] flex items-center justify-center" role="dialog" aria-modal="true"
      aria-label={block.title ? `${block.title} (full page)` : 'Flow (full page)'}>
      {/* Backdrop — click to close; also blurs the page behind it. */}
      <button aria-label="Close full page flow" onClick={onClose} className="absolute inset-0 cursor-pointer bg-black/70 backdrop-blur-md" />

      <div className="glass-card-strong relative z-10 flex h-[90vh] w-[94vw] max-w-6xl flex-col overflow-hidden rounded-2xl border border-white/10">
        <div className="flex shrink-0 items-center justify-between gap-2 border-b border-white/10 px-4 py-2.5">
          <span className="truncate font-mono text-[10px] uppercase tracking-widest text-muted-foreground/70">
            Flow · full page
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
          {(block.title || block.description) && (
            <div className="mb-6 border-b border-border/40 pb-3 text-center">
              {block.title && <h3 className="text-lg font-semibold tracking-tight text-foreground">{block.title}</h3>}
              {block.description && <p className="mt-1 text-[13px] text-muted-foreground">{block.description}</p>}
            </div>
          )}
          <FlowSteps block={block} large />
        </div>
      </div>
    </div>
  );

  return typeof document !== 'undefined' ? createPortal(overlay, document.body) : null;
}

function FullPageButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title="View flow full page"
      aria-label="View flow full page"
      className="inline-flex items-center gap-1 whitespace-nowrap rounded-full border border-border/50 bg-accent/30 px-2.5 py-1 text-[11px] text-muted-foreground transition-colors hover:bg-accent/60 hover:text-foreground"
    >
      <Maximize2 size={12} /> Full page
    </button>
  );
}

export function FlowBlock({ block }: { block: FlowBlockType }) {
  const [full, setFull] = useState(false);
  const openFull = useCallback(() => setFull(true), []);
  const closeFull = useCallback(() => setFull(false), []);
  const hasHeading = Boolean(block.title || block.description);

  return (
    <>
      <div className="glass-card mx-auto w-full max-w-3xl rounded-xl p-5">
        {hasHeading ? (
          // Three equal-ish columns keep the heading truly centred while the
          // "Full page" button sits in its own column (no overlap, no offset).
          <div className="mb-4 grid grid-cols-[1fr_auto_1fr] items-center gap-2 border-b border-border/40 pb-3">
            <span aria-hidden="true" />
            <div className="min-w-0 text-center">
              {block.title && (
                <h3 className="break-words text-base font-semibold tracking-tight text-foreground" title={block.title}>
                  {block.title}
                </h3>
              )}
              {block.description && <p className="mt-1 text-[12.5px] text-muted-foreground">{block.description}</p>}
            </div>
            <div className="justify-self-end">
              <FullPageButton onClick={openFull} />
            </div>
          </div>
        ) : (
          <div className="mb-3 flex justify-end">
            <FullPageButton onClick={openFull} />
          </div>
        )}
        <FlowSteps block={block} />
      </div>
      {full && <FlowViewer block={block} onClose={closeFull} />}
    </>
  );
}

export default FlowBlock;

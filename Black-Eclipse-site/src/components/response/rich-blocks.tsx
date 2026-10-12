'use client';

// ── Rich response blocks ───────────────────────────────────────────────────────
// Process / report / action / artifact blocks. Presentational only: they render
// *validated* data and never execute model output. Interactions either re-enter
// the existing agent loop (actions) or link to the existing Artifact Center
// (artifacts) — no privileged backend calls.

import { useState, type ReactNode } from 'react';
import {
  Check,
  ChevronRight,
  Download,
  ExternalLink,
  FileText,
  Play,
  type LucideIcon,
} from '@/lib/icons';
import { cn } from '@/lib/utils';
import { Markdown } from '@/components/chat/markdown';
import { resolveResponseIcon } from '@/lib/response/icons';
import { downloadUrl } from '@/lib/harness/artifacts-browser';
import type {
  ActionGroupBlock as ActionGroupBlockType,
  ArtifactBlock as ArtifactBlockType,
  InfographicBlock as InfographicBlockType,
  ReportBlock as ReportBlockType,
  StepperBlock as StepperBlockType,
  ValidatedBlock,
} from '@/lib/response/contract';

type Tone = 'neutral' | 'info' | 'success' | 'warning' | 'danger';

const TONE_TEXT: Record<Tone, string> = {
  neutral: 'text-muted-foreground',
  info: 'text-sky-300',
  success: 'text-emerald-300',
  warning: 'text-amber-300',
  danger: 'text-rose-300',
};

const TONE_RING: Record<Tone, string> = {
  neutral: 'ring-border/50 text-muted-foreground',
  info: 'ring-sky-500/40 text-sky-300',
  success: 'ring-emerald-500/40 text-emerald-300',
  warning: 'ring-amber-500/40 text-amber-300',
  danger: 'ring-rose-500/40 text-rose-300',
};

// ── Stepper ─────────────────────────────────────────────────────────────────────

const STEP_STATUS: Record<string, { ring: string; label: string }> = {
  pending: { ring: 'ring-border/60 text-muted-foreground', label: 'Pending' },
  active: { ring: 'ring-sky-500/60 text-sky-300', label: 'In progress' },
  done: { ring: 'ring-emerald-500/60 text-emerald-300', label: 'Done' },
  error: { ring: 'ring-rose-500/60 text-rose-300', label: 'Blocked' },
};

export function StepperBlock({ block }: { block: StepperBlockType }) {
  return (
    <div className="w-full">
      {block.title && <h4 className="mb-1 text-sm font-semibold text-foreground">{block.title}</h4>}
      {block.description && <p className="mb-2 text-[12px] text-muted-foreground">{block.description}</p>}
      <ol className="space-y-2">
        {block.steps.map((step, i) => {
          const status = STEP_STATUS[step.status] ?? STEP_STATUS.pending;
          return (
            <li key={i} className="flex gap-3">
              <div className="flex flex-col items-center">
                <span
                  className={cn(
                    'flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold ring-1',
                    status.ring,
                  )}
                  aria-label={`Step ${i + 1}: ${status.label}`}
                >
                  {step.status === 'done' ? <Check size={12} /> : i + 1}
                </span>
                {i < block.steps.length - 1 && <span className="mt-1 w-px flex-1 bg-border/40" />}
              </div>
              <div className="min-w-0 pb-1">
                <p className="text-[13px] font-medium text-foreground">{step.title}</p>
                {step.description && (
                  <Markdown content={step.description} compact className="mt-0.5 text-[12px] text-muted-foreground" />
                )}
                {step.hint && <p className="mt-0.5 text-[10px] text-muted-foreground/60">{step.hint}</p>}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

// ── Infographic (icon cards) ─────────────────────────────────────────────────────

export function InfographicBlock({ block }: { block: InfographicBlockType }) {
  const cols = block.columns ?? Math.min(block.cards.length, 3);
  const gridClass =
    cols <= 1
      ? 'grid-cols-1'
      : cols === 2
        ? 'grid-cols-1 sm:grid-cols-2'
        : cols === 3
          ? 'grid-cols-1 sm:grid-cols-3'
          : 'grid-cols-2 md:grid-cols-4';
  return (
    <div className="w-full">
      {block.title && <h4 className="mb-1.5 text-sm font-semibold text-foreground">{block.title}</h4>}
      {block.description && <p className="mb-2 text-[12px] text-muted-foreground">{block.description}</p>}
      <div className={cn('grid gap-2.5', gridClass)}>
        {block.cards.map((card, i) => {
          const Icon: LucideIcon = resolveResponseIcon(card.icon);
          return (
            <div key={i} className="glass-card-subtle rounded-xl px-3 py-3">
              <div className="flex items-center gap-2">
                <span className={cn('flex h-7 w-7 items-center justify-center rounded-lg bg-accent/40 ring-1', TONE_RING[card.tone])}>
                  <Icon size={15} />
                </span>
                <p className="truncate text-[12px] font-medium text-foreground" title={card.label}>
                  {card.label}
                </p>
              </div>
              {card.value != null && (
                <div className="mt-2 flex items-baseline gap-1">
                  {card.unavailable ? (
                    <span className="rounded border border-border/50 bg-accent/20 px-1.5 py-0.5 text-[0.7em] font-medium uppercase tracking-wide text-muted-foreground/80">
                      UNAVAILABLE
                    </span>
                  ) : (
                    <>
                      <span className="text-[17px] font-semibold tabular-nums leading-none text-foreground">
                        {typeof card.value === 'number' ? card.value.toLocaleString() : card.value}
                      </span>
                      {card.unit && <span className="text-[11px] text-muted-foreground">{card.unit}</span>}
                    </>
                  )}
                </div>
              )}
              {card.description && (
                <p className="mt-1.5 text-[11px] leading-snug text-muted-foreground/80">{card.description}</p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Report (sectioned container) ─────────────────────────────────────────────────

export function ReportBlock({
  block,
  renderBlocks,
}: {
  block: ReportBlockType;
  renderBlocks: (blocks: ValidatedBlock[]) => ReactNode;
}) {
  return (
    <article className="w-full">
      {block.title && <h3 className="text-base font-semibold tracking-tight text-foreground">{block.title}</h3>}
      {block.summary && <p className="mt-0.5 text-[13px] text-muted-foreground">{block.summary}</p>}
      <div className="mt-3 space-y-4">
        {block.sections.map((section, i) => (
          <section key={i} className={cn('border-l-2 pl-3', section.tone === 'neutral' ? 'border-border/40' : TONE_TEXT[section.tone])}>
            {section.heading && <h4 className="mb-1 text-[13px] font-semibold text-foreground">{section.heading}</h4>}
            {section.markdown && <Markdown content={section.markdown} compact className="text-[13px]" />}
            {section.blocks && section.blocks.length > 0 && (
              <div className="mt-2">{renderBlocks(section.blocks as ValidatedBlock[])}</div>
            )}
          </section>
        ))}
      </div>
    </article>
  );
}

// ── Action group (proposed next steps) ───────────────────────────────────────────

export function ActionGroupBlock({
  block,
  onFollowup,
}: {
  block: ActionGroupBlockType;
  onFollowup?: (prompt: string) => void;
}) {
  const [sent, setSent] = useState<Record<string, boolean>>({});
  const run = (id: string, prompt: string) => {
    if (!onFollowup) return;
    onFollowup(prompt);
    setSent((s) => ({ ...s, [id]: true }));
  };
  return (
    <div className="w-full rounded-xl border border-white/10 bg-accent/10 p-3">
      <div className="mb-1 flex items-center gap-1.5">
        <ChevronRight size={13} className="text-muted-foreground" />
        <h4 className="text-sm font-semibold text-foreground">{block.title ?? 'Suggested next steps'}</h4>
        <span className="rounded border border-border/50 px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-muted-foreground/70">
          Proposed
        </span>
      </div>
      {block.description && <p className="mb-2 text-[12px] text-muted-foreground">{block.description}</p>}
      <div className="flex flex-col gap-1.5">
        {block.actions.map((action) => {
          const Icon = resolveResponseIcon(action.icon);
          const done = sent[action.id];
          return (
            <button
              key={action.id}
              type="button"
              onClick={() => run(action.id, action.prompt)}
              disabled={!onFollowup || done}
              className={cn(
                'group flex items-start gap-2 rounded-lg border border-border/50 px-2.5 py-2 text-left transition-colors',
                !onFollowup ? 'cursor-not-allowed opacity-50' : done ? 'opacity-60' : 'hover:bg-accent/60',
              )}
            >
              <span className={cn('mt-0.5 shrink-0', TONE_TEXT[action.tone])}>
                {done ? <Check size={14} /> : <Icon size={14} />}
              </span>
              <span className="min-w-0">
                <span className="block text-[12.5px] font-medium text-foreground">{action.label}</span>
                {action.description && (
                  <span className="mt-0.5 block text-[11px] text-muted-foreground/80">{action.description}</span>
                )}
              </span>
              {!done && onFollowup && <Play size={11} className="ml-auto mt-0.5 shrink-0 opacity-0 transition-opacity group-hover:opacity-60" />}
            </button>
          );
        })}
      </div>
      <p className="mt-2 text-[10px] text-muted-foreground/60">
        {onFollowup
          ? 'Sends the action as a new turn — nothing runs until you choose one.'
          : 'Actions are unavailable in this view.'}
      </p>
    </div>
  );
}

// ── Artifact reference ────────────────────────────────────────────────────────────

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function ArtifactBlock({ block }: { block: ArtifactBlockType }) {
  return (
    <div className="w-full">
      {block.title && <h4 className="mb-1.5 text-sm font-semibold text-foreground">{block.title}</h4>}
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {block.artifacts.map((artifact, i) => {
          const href = artifact.artifactId
            ? downloadUrl(artifact.artifactId, artifact.version)
            : artifact.url;
          return (
            <div key={i} className="glass-card-subtle flex items-start gap-2.5 rounded-xl px-3 py-2.5">
              <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent/40 text-muted-foreground">
                <FileText size={15} />
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-[12.5px] font-medium text-foreground" title={artifact.name}>
                  {artifact.name}
                </p>
                <div className="flex flex-wrap items-center gap-x-2 text-[10px] text-muted-foreground/60">
                  {artifact.category && <span>{artifact.category}</span>}
                  {artifact.version != null && <span>v{artifact.version}</span>}
                  {artifact.sizeBytes != null && <span>{formatBytes(artifact.sizeBytes)}</span>}
                  {artifact.mimeType && <span>{artifact.mimeType}</span>}
                </div>
                {artifact.description && <p className="mt-0.5 line-clamp-2 text-[11px] text-muted-foreground/80">{artifact.description}</p>}
                {href && (
                  <a
                    href={href}
                    {...(artifact.artifactId ? { download: true } : { target: '_blank', rel: 'noopener noreferrer' })}
                    className="mt-1 inline-flex items-center gap-1 text-[11px] text-primary underline underline-offset-2 hover:opacity-80"
                  >
                    {artifact.artifactId ? <Download size={11} /> : <ExternalLink size={11} />}
                    {artifact.artifactId ? 'Download' : 'Open'}
                  </a>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

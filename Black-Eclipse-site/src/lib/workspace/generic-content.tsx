'use client';

// ── Generic content widgets ──────────────────────────────────────────────────
// Content-only primitives an agent can compose onto any page: `markdown`,
// `list`, `status-indicator`, `empty-state`, `error-state`. They render the
// blueprint's config verbatim (no code execution, no HTML injection) and, where
// they read a source, use the SAME allow-listed resolver as the data widgets.

import React from 'react';
import { cn } from '@/lib/utils';
import { FileText, List, HeartPulse, Inbox, AlertTriangle } from '@/lib/icons';
import type { WidgetPlacement } from '@/lib/workspace/types';
import { useDataSource } from '@/lib/workspace/data-source';

function str(v: unknown): string {
  return typeof v === 'string' ? v : '';
}

function Header({ icon: Icon, title, hint }: {
  icon: React.ComponentType<{ size?: number; className?: string }>;
  title: string;
  hint?: string;
}) {
  return (
    <div className="flex items-center justify-between gap-2 border-b border-border/10 pb-2.5 mb-3">
      <div className="flex min-w-0 items-center gap-2">
        <Icon size={14} className="shrink-0 text-primary" />
        <h3 className="truncate font-serif text-sm font-semibold text-foreground">{title}</h3>
      </div>
      {hint && <span className="shrink-0 font-mono text-[9px] text-muted-foreground/70">{hint}</span>}
    </div>
  );
}

// ── markdown — a small, safe subset (no HTML) ────────────────────────────────

function renderInline(text: string, key: number): React.ReactNode {
  // Bold **…** and inline `code` only; everything else is plain text.
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean);
  return (
    <React.Fragment key={key}>
      {parts.map((part, i) => {
        if (part.startsWith('**') && part.endsWith('**')) return <strong key={i}>{part.slice(2, -2)}</strong>;
        if (part.startsWith('`') && part.endsWith('`')) return <code key={i} className="rounded bg-white/[0.06] px-1 font-mono text-[0.85em]">{part.slice(1, -1)}</code>;
        return part;
      })}
    </React.Fragment>
  );
}

function MarkdownBody({ text }: { text: string }) {
  const lines = text.split('\n');
  return (
    <div className="flex flex-col gap-2 text-sm leading-relaxed text-foreground/90">
      {lines.map((line, i) => {
        const trimmed = line.trim();
        if (!trimmed) return <span key={i} className="h-1" />;
        if (trimmed.startsWith('### ')) return <h4 key={i} className="font-serif text-sm font-semibold">{renderInline(trimmed.slice(4), i)}</h4>;
        if (trimmed.startsWith('## ')) return <h3 key={i} className="font-serif text-base font-semibold">{renderInline(trimmed.slice(3), i)}</h3>;
        if (trimmed.startsWith('# ')) return <h2 key={i} className="font-serif text-lg font-semibold">{renderInline(trimmed.slice(2), i)}</h2>;
        if (/^[-*] /.test(trimmed)) return <p key={i} className="pl-4 before:mr-2 before:content-['•']">{renderInline(trimmed.slice(2), i)}</p>;
        return <p key={i}>{renderInline(trimmed, i)}</p>;
      })}
    </div>
  );
}

export function MarkdownWidget({ placement }: { placement: WidgetPlacement }) {
  const text = str((placement.config ?? {}).text);
  return (
    <div className="flex h-full flex-col p-4">
      <Header icon={FileText} title={str((placement.config ?? {}).title) || 'Markdown'} />
      <div className="flex-1 overflow-y-auto custom-scrollbar">
        {text ? <MarkdownBody text={text} /> : <p className="text-xs italic text-muted-foreground/70">No content.</p>}
      </div>
    </div>
  );
}

// ── list — a compact card list over any row source ───────────────────────────

export function ListWidget({ placement }: { placement: WidgetPlacement }) {
  const cfg = (placement.config ?? {}) as Record<string, unknown>;
  const source = str(cfg.source) || (str(cfg.portfolioId) ? `portfolio:${str(cfg.portfolioId)}:positions` : '');
  const entry = useDataSource(source || undefined);
  const data = entry.data;
  const title = str(cfg.title) || 'List';
  const rows = data?.rows ?? [];
  const columns = data?.columns ?? [];

  if (!source || data?.kind === 'unavailable') {
    return (
      <div className="flex h-full flex-col p-4">
        <Header icon={List} title={title} />
        <div className="flex flex-1 items-center justify-center text-center">
          <p className="max-w-[28ch] text-xs italic text-amber-400/80">{data?.detail || 'UNAVAILABLE — no data source configured.'}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col p-4">
      <Header icon={List} title={title} hint={rows.length ? `${rows.length} items` : undefined} />
      {rows.length === 0 ? (
        <p className="py-6 text-center text-xs italic text-muted-foreground/70">No items.</p>
      ) : (
        <div className="flex-1 overflow-y-auto custom-scrollbar flex flex-col gap-1.5">
          {rows.map((row, i) => (
            <div key={i} className="rounded-xl glass-card-subtle px-3 py-2">
              <div className="flex items-baseline justify-between gap-2">
                <span className="truncate font-mono text-xs font-bold text-foreground">
                  {String(row[columns[0]?.key] ?? '—')}
                </span>
                {columns[1] && <span className="shrink-0 font-mono text-[10px] text-muted-foreground">{String(row[columns[1].key] ?? '')}</span>}
              </div>
              {columns[2] && <p className="mt-0.5 truncate text-[11px] text-muted-foreground">{String(row[columns[2].key] ?? '')}</p>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── status-indicator ─────────────────────────────────────────────────────────

const STATUS_STYLE: Record<string, string> = {
  ok: 'border-emerald-500/25 bg-emerald-500/10 text-emerald-400',
  warning: 'border-amber-500/25 bg-amber-500/10 text-amber-400',
  error: 'border-rose-500/25 bg-rose-500/10 text-rose-400',
  unknown: 'border-border/30 bg-white/[0.04] text-muted-foreground',
};

export function StatusIndicatorWidget({ placement }: { placement: WidgetPlacement }) {
  const cfg = (placement.config ?? {}) as Record<string, unknown>;
  const status = str(cfg.status) || 'unknown';
  const label = str(cfg.label) || status;
  return (
    <div className="flex h-full flex-col p-4">
      <Header icon={HeartPulse} title={str(cfg.title) || 'Status'} />
      <div className="flex flex-1 items-center justify-center">
        <span className={cn('rounded-full border px-3 py-1 font-mono text-xs font-bold uppercase tracking-wide', STATUS_STYLE[status] ?? STATUS_STYLE.unknown)}>
          {label}
        </span>
      </div>
    </div>
  );
}

// ── empty-state / error-state ────────────────────────────────────────────────

export function EmptyStateWidget({ placement }: { placement: WidgetPlacement }) {
  const cfg = (placement.config ?? {}) as Record<string, unknown>;
  return (
    <div className="flex h-full flex-col p-4">
      <Header icon={Inbox} title={str(cfg.title) || 'Nothing here'} />
      <div className="flex flex-1 items-center justify-center text-center">
        <p className="max-w-[30ch] text-xs italic text-muted-foreground/70">{str(cfg.message) || 'A deliberate empty placeholder.'}</p>
      </div>
    </div>
  );
}

export function ErrorStateWidget({ placement }: { placement: WidgetPlacement }) {
  const cfg = (placement.config ?? {}) as Record<string, unknown>;
  return (
    <div className="flex h-full flex-col p-4">
      <Header icon={AlertTriangle} title={str(cfg.title) || 'Something went wrong'} />
      <div className="flex flex-1 items-center justify-center text-center">
        <p className="max-w-[30ch] text-xs italic text-amber-400/80">{str(cfg.message) || 'A recoverable error placeholder.'}</p>
      </div>
    </div>
  );
}

'use client';

import { useId, useState } from 'react';
import { ChevronDown, ChevronRight, FileText, AlertTriangle, Table2, ScanEye, ShieldAlert } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { coerceDocumentRun, primaryDocument } from '@/lib/harness/document-view';
import type { DocumentRunDocument } from '@/lib/harness/types';

/**
 * The document panel — the right-sidebar context for a turn that used the
 * document-intelligence capability. Mirrors `VisionPanel`/`ResearchEvidencePanel`:
 * one always-visible summary line (document type, pages, status) that expands to
 * the per-capability processing status, current page/section context, evidence
 * and entity detail. Every value comes from the run's collected document blob;
 * nothing is inferred, and an absent/odd blob renders nothing.
 */

const CAPABILITY_LABELS: Record<string, string> = {
  text: 'Text',
  structure: 'Structure',
  tables: 'Tables',
  images: 'Images',
  ocr: 'OCR',
  vision: 'Vision',
};

const FAIL = new Set(['FAIL', 'UNAVAILABLE']);

export function DocumentPanel({ documents, compact = false }: { documents: unknown; compact?: boolean }) {
  const run = coerceDocumentRun(documents);
  const [open, setOpen] = useState(false);
  const bodyId = useId();
  if (!run) return null;
  const primary = primaryDocument(run);
  if (!primary && !run.failures?.length) return null;

  const failureCount = run.failures?.length ?? 0;
  const summary = primary
    ? [
        primary.kind?.toUpperCase(),
        primary.pageCount ? `${primary.pageCount} pages` : undefined,
        primary.sheetCount ? `${primary.sheetCount} sheets` : undefined,
        primary.state?.replace(/_/g, ' ').toLowerCase(),
      ]
        .filter(Boolean)
        .join(' · ')
    : `${failureCount} document${failureCount === 1 ? '' : 's'} unavailable`;

  return (
    <div className={cn('mt-3 w-full rounded-xl border border-border/20 glass-card-subtle', compact ? 'p-2' : 'p-2.5')}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={bodyId}
        className="flex w-full flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground transition-colors hover:text-foreground cursor-pointer"
      >
        {open ? <ChevronDown size={11} className="shrink-0" /> : <ChevronRight size={11} className="shrink-0" />}
        <FileText size={11} className="shrink-0 text-primary" />
        <span className="font-medium text-foreground/90">Document</span>
        <span className="truncate text-muted-foreground/80">{primary?.title || primary?.fileName || summary}</span>
        {primary ? <span className="text-muted-foreground/60">· {summary}</span> : null}
        {failureCount > 0 ? <span className="text-amber-500/90">· {failureCount} unavailable</span> : null}
      </button>

      {open ? (
        <div id={bodyId} className="mt-2.5 space-y-3 text-[10px]">
          {primary ? <DocumentDetail document={primary} /> : null}
          {failureCount > 0 && (
            <section>
              <div className="flex items-center gap-1.5 px-1">
                <AlertTriangle size={11} className="shrink-0 text-amber-500" />
                <span className="font-semibold text-foreground">Unavailable</span>
              </div>
              <ul className="mt-1.5 space-y-1 pl-4">
                {run.failures?.map((f, i) => {
                  const code =
                    f.error && typeof f.error === 'object' && 'errorClass' in (f.error as Record<string, unknown>)
                      ? String((f.error as Record<string, unknown>).errorClass)
                      : 'ERROR';
                  return (
                    <li key={i} className="text-muted-foreground/90">
                      <span className="text-foreground/80">{f.kind ?? 'document'}</span> — {code}
                    </li>
                  );
                })}
              </ul>
            </section>
          )}
        </div>
      ) : null}
    </div>
  );
}

function DocumentDetail({ document }: { document: DocumentRunDocument }) {
  return (
    <>
      <section className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 px-1 text-muted-foreground/90">
        <span className="text-muted-foreground/60">Document</span>
        <span className="truncate font-mono text-foreground/80">{document.documentId}</span>
        {document.state ? (
          <>
            <span className="text-muted-foreground/60">Status</span>
            <span className="text-foreground/80">{document.state.replace(/_/g, ' ')}</span>
          </>
        ) : null}
        {document.textMethod ? (
          <>
            <span className="text-muted-foreground/60">Method</span>
            <span className="text-foreground/80">{document.textMethod}</span>
          </>
        ) : null}
        {typeof document.confidence === 'number' ? (
          <>
            <span className="text-muted-foreground/60">Confidence</span>
            <span className="text-foreground/80">{document.confidence.toFixed(2)}</span>
          </>
        ) : null}
        {document.currentContext?.page !== undefined ? (
          <>
            <span className="text-muted-foreground/60">Context</span>
            <span className="text-foreground/80">
              page {document.currentContext.page}
              {document.currentContext.section ? ` · ${document.currentContext.section}` : ''}
            </span>
          </>
        ) : null}
      </section>

      {document.capabilities ? (
        <section>
          <div className="flex items-center gap-1.5 px-1">
            <FileText size={11} className="shrink-0 text-primary" />
            <span className="font-semibold text-foreground">Processing</span>
          </div>
          <ul className="mt-1.5 grid grid-cols-1 gap-x-3 gap-y-0.5 px-1 sm:grid-cols-2">
            {Object.entries(document.capabilities).map(([key, value]) => (
              <li key={key} className="flex items-center gap-1.5">
                <span className={cn(FAIL.has(value) ? 'text-amber-500/90' : 'text-emerald-500/90')}>
                  {FAIL.has(value) ? '✗' : '✓'}
                </span>
                <span className="text-muted-foreground/80">{CAPABILITY_LABELS[key] ?? key}</span>
                {FAIL.has(value) ? <span className="text-muted-foreground/60">({value.toLowerCase()})</span> : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {document.tableCount || document.evidenceCount || document.imageCount ? (
        <section className="flex flex-wrap items-center gap-x-3 gap-y-0.5 px-1 text-muted-foreground/90">
          <Table2 size={11} className="shrink-0 text-primary" />
          {document.tableCount ? <span>{document.tableCount} table(s)</span> : null}
          {document.imageCount ? <span>{document.imageCount} image(s)</span> : null}
          {document.evidenceCount ? <span>{document.evidenceCount} evidence passage(s)</span> : null}
        </section>
      ) : null}

      {document.entities && document.entities.length > 0 ? (
        <section>
          <div className="flex items-center gap-1.5 px-1">
            <ScanEye size={11} className="shrink-0 text-primary" />
            <span className="font-semibold text-foreground">Entities</span>
            <span className="text-muted-foreground/70">· {document.entities.length}</span>
          </div>
          <div className="mt-1.5 flex flex-wrap gap-1 px-1">
            {document.entities.slice(0, 24).map((entity, i) => (
              <span key={i} className="rounded-md border border-border/20 px-1.5 py-0.5 text-foreground/80">
                {entity.value}
              </span>
            ))}
          </div>
        </section>
      ) : null}

      {document.warnings && document.warnings.length > 0 ? (
        <ul className="space-y-0.5 px-1">
          {document.warnings.slice(0, 5).map((w, i) => (
            <li key={i} className="flex items-start gap-1.5 text-amber-500/90">
              <ShieldAlert size={11} className="mt-0.5 shrink-0" />
              <span className="break-words">{w}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </>
  );
}

'use client';

import dynamic from 'next/dynamic';
import type { ComponentType } from 'react';
import { Code, Download, Loader2, Play, Trash2 } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n/use-t';
import type { NotebookCell as NotebookCellModel } from '@/lib/chat/notebook-types';

interface MonacoProps {
  value: string;
  language?: string;
  theme?: string;
  height?: string | number;
  onChange?: (value: string | undefined) => void;
  options?: Record<string, unknown>;
}

// Monaco is heavy and browser-only. The notebook is opened on demand, so the
// editor is code-split with it instead of entering the chat bundle.
const MonacoEditor = dynamic(
  () => import('@monaco-editor/react').then((mod) => mod.Editor),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-[180px] items-center justify-center text-xs text-muted-foreground">
        Loading editor…
      </div>
    ),
  },
) as unknown as ComponentType<MonacoProps>;

const STATUS_STYLE: Record<string, string> = {
  idle: 'border-border/40 text-muted-foreground',
  running: 'border-primary/40 text-primary',
  ok: 'border-emerald-400/40 text-emerald-300',
  failed: 'border-rose-400/40 text-rose-300',
  refused: 'border-amber-400/40 text-amber-300',
  timed_out: 'border-amber-400/40 text-amber-300',
};

function valueText(value: unknown): string {
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function NotebookCellView({
  cell,
  index,
  busy,
  onChange,
  onRun,
  onDelete,
}: {
  cell: NotebookCellModel;
  index: number;
  busy: boolean;
  onChange: (id: string, source: string) => void;
  onRun: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  const t = useT();
  const rows = Object.entries(cell.outputs ?? {}).filter(([key]) => !key.startsWith('_'));
  const images = cell.artifacts.filter(
    (artifact) => artifact.downloadUrl && artifact.mimeType.toLowerCase().startsWith('image/'),
  );
  const files = cell.artifacts.filter(
    (artifact) => artifact.downloadUrl && !artifact.mimeType.toLowerCase().startsWith('image/'),
  );
  const running = busy || cell.status === 'running';

  return (
    <article className="rounded-xl border border-border/30 bg-black/10 p-2.5">
      <header className="mb-1.5 flex flex-wrap items-center gap-1.5">
        <Code size={12} className="shrink-0 text-primary" />
        <span className="text-[11px] font-medium text-foreground">
          {t('notebook.cellLabel', { n: String(index + 1) })}
        </span>
        {cell.chartBlockId && (
          <span className="rounded-full border border-border/40 px-1.5 py-0.5 text-[9px] text-muted-foreground">
            {t('notebook.fromChart')}
          </span>
        )}
        <span
          className={cn(
            'rounded-full border px-1.5 py-0.5 text-[9px]',
            STATUS_STYLE[cell.status] ?? STATUS_STYLE.idle,
          )}
        >
          {t(`notebook.status.${cell.status}` as 'notebook.status.idle')}
        </span>
        <span className="ml-auto flex items-center gap-1">
          <button
            type="button"
            disabled={running}
            onClick={() => onRun(cell.id)}
            className="flex items-center gap-1 rounded-md border border-border/50 px-2 py-1 text-[10px] text-foreground transition-colors hover:bg-accent disabled:opacity-40"
          >
            {running ? <Loader2 size={11} className="animate-spin" /> : <Play size={11} />}
            {running ? t('notebook.running') : t('notebook.run')}
          </button>
          <button
            type="button"
            onClick={() => onDelete(cell.id)}
            aria-label={t('notebook.delete')}
            className="flex h-6 w-6 items-center justify-center rounded-md border border-border/40 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <Trash2 size={11} />
          </button>
        </span>
      </header>

      <div className="overflow-hidden rounded-lg border border-border/30 bg-black/30">
        <MonacoEditor
          value={cell.source}
          language="python"
          theme="vs-dark"
          height={Math.min(320, Math.max(150, cell.source.split('\n').length * 18 + 24))}
          onChange={(value) => onChange(cell.id, value ?? '')}
          options={{
            minimap: { enabled: false },
            lineNumbers: 'on',
            scrollBeyondLastLine: false,
            fontSize: 12,
            fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
            padding: { top: 8, bottom: 8 },
            automaticLayout: true,
            wordWrap: 'on',
            tabSize: 4,
          }}
        />
      </div>

      {cell.error ? (
        <p className="mt-2 rounded-md border border-rose-400/25 bg-rose-500/5 p-2 text-[10px] text-rose-200">
          {cell.error}
        </p>
      ) : null}

      {images.length > 0 && (
        <div className="mt-2 space-y-1.5">
          {images.map((artifact) => (
            <figure key={artifact.id ?? artifact.name}>
              <img
                src={artifact.downloadUrl ?? ''}
                alt={artifact.name}
                className="max-h-72 w-auto rounded-lg border border-border/30"
              />
              <figcaption className="mt-0.5 text-[9px] text-muted-foreground/70">{artifact.name}</figcaption>
            </figure>
          ))}
        </div>
      )}

      {cell.figure && (
        <p className="mt-1 text-[9px] text-muted-foreground/70">
          {t('notebook.figure')}: {cell.figure.kind}
          {cell.figure.series?.length
            ? ` · ${cell.figure.series.map((s) => `${s.name} (${s.points})`).join(', ')}`
            : ''}
        </p>
      )}

      {rows.length > 0 && (
        <div className="mt-2">
          <p className="mb-0.5 text-[9px] font-medium uppercase tracking-wider text-muted-foreground/60">
            {t('notebook.output')}
          </p>
          <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-md border border-border/30 bg-black/30 p-2 font-mono text-[10px] text-foreground/90">
            {rows.map(([key, value]) => `${key}: ${valueText(value)}`).join('\n')}
          </pre>
        </div>
      )}

      {files.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {files.map((artifact) => (
            <a
              key={artifact.id ?? artifact.name}
              href={artifact.downloadUrl ?? '#'}
              className="inline-flex items-center gap-1 rounded-md border border-border/40 px-1.5 py-0.5 text-[10px] text-muted-foreground hover:bg-white/5 hover:text-foreground"
            >
              <Download size={10} />
              {artifact.name}
            </a>
          ))}
        </div>
      )}
    </article>
  );
}

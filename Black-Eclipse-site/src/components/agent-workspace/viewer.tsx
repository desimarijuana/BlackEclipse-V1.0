'use client';

// ── Agent Workspace — large-output Viewer ─────────────────────────────────────
// The dedicated surface for a large output/artifact, so huge terminal output,
// JSON, logs or diffs never flood chat. Content is fetched lazily and rendered
// with a windowed list (only what is on screen is mounted), so a 100k-line
// artifact cannot create 100k DOM nodes.
//
// Copy is honest: when the runtime persisted only a truncated copy, the viewer
// says so — it never pretends to have the full text it does not have.

import { useEffect, useMemo, useState } from 'react';
import { Check, Copy, Loader2 } from '@/lib/icons';
import { useT } from '@/lib/i18n';
import { Markdown } from '@/components/chat/markdown';
import type { ArtifactRef } from '@/lib/agent-workspace/types';
import { formatBytes, formatCount } from '@/lib/agent-workspace/format';

export interface LoadedContent {
  content: string;
  /** True when the runtime only retained a truncated copy. */
  truncated: boolean;
}

const LINE_WINDOW = 400;
const LINE_STEP = 400;

export function ArtifactViewer({
  artifact,
  load,
  onClose,
}: {
  artifact: ArtifactRef;
  load?: (artifact: ArtifactRef) => Promise<LoadedContent | null>;
  onClose: () => void;
}) {
  const t = useT();
  const [loaded, setLoaded] = useState<LoadedContent | null>(null);
  const [loading, setLoading] = useState(false);
  const [lines, setLines] = useState(LINE_WINDOW);

  useEffect(() => {
    if (!load) return;
    let alive = true;
    setLoading(true);
    setLoaded(null);
    load(artifact)
      .then((res) => {
        if (alive) setLoaded(res);
      })
      .catch(() => {
        if (alive) setLoaded(null);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [artifact, load]);

  const rendered = useMemo(() => {
    if (!loaded) return null;
    if (artifact.type === 'markdown' || artifact.type === 'report') {
      return <Markdown content={loaded.content} />;
    }
    if (artifact.type === 'json') {
      return <JsonBody content={loaded.content} />;
    }
    const all = loaded.content.split('\n');
    const slice = all.slice(0, lines);
    return (
      <div className="font-mono text-[11.5px] leading-relaxed">
        {slice.map((line, i) => (
          <div key={i} className="flex">
            <span className="mr-3 w-10 shrink-0 select-none text-right text-muted-foreground/30 tabular-nums">{i + 1}</span>
            <span className="min-w-0 flex-1 whitespace-pre-wrap break-all text-foreground/85">{line}</span>
          </div>
        ))}
        {all.length > lines && (
          <button
            type="button"
            onClick={() => setLines((v) => v + LINE_STEP)}
            className="mt-2 w-full rounded-lg py-1 text-center text-[11px] text-muted-foreground hover:bg-white/[0.04] hover:text-foreground"
          >
            ↓ {all.length - lines} more lines
          </button>
        )}
      </div>
    );
  }, [loaded, artifact.type, lines]);

  return (
    <div role="dialog" aria-label={artifact.name} className="flex h-full min-h-0 flex-col">
      <header className="flex items-center gap-2 border-b border-white/10 px-3 py-2">
        <span className="min-w-0 flex-1 truncate text-[12px] font-medium text-foreground">{artifact.name}</span>
        <span className="shrink-0 rounded-md border border-white/10 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground/70">
          {artifact.type}
        </span>
        {artifact.sizeBytes != null && <span className="shrink-0 text-[10px] text-muted-foreground/50">{formatBytes(artifact.sizeBytes)}</span>}
        <CopyButton content={loaded?.content} />
        <button type="button" onClick={onClose} className="shrink-0 rounded-lg px-2 py-1 text-[11px] text-muted-foreground hover:bg-white/[0.04] hover:text-foreground">
          {t('common.close')}
        </button>
      </header>
      <div className="min-h-0 flex-1 overflow-auto p-3">
        {loading ? (
          <div className="flex items-center gap-2 py-6 text-[12px] text-muted-foreground/60">
            <Loader2 size={13} className="animate-spin" /> {t('common.loading')}
          </div>
        ) : loaded ? (
          rendered
        ) : (
          <div className="space-y-1 py-3 text-[12px] text-muted-foreground/60">
            <p>{t('workspace.notAvailable')}</p>
            {artifact.preview && <p className="font-mono text-[11px] text-muted-foreground/50">{artifact.preview}</p>}
            {artifact.storageRef && <p className="font-mono text-[10px] text-muted-foreground/40">{artifact.storageRef}</p>}
          </div>
        )}
      </div>
      {loaded?.truncated && (
        <footer className="border-t border-white/10 px-3 py-1.5 text-[10.5px] text-amber-300/80">
          Only the first {formatCount(loaded.content.length)} characters were retained by the runtime.
        </footer>
      )}
    </div>
  );
}

function JsonBody({ content }: { content: string }) {
  const pretty = useMemo(() => {
    try {
      return JSON.stringify(JSON.parse(content), null, 2);
    } catch {
      return content;
    }
  }, [content]);
  return <pre className="whitespace-pre-wrap break-all font-mono text-[11.5px] leading-relaxed text-foreground/85">{pretty}</pre>;
}

function CopyButton({ content }: { content?: string }) {
  const t = useT();
  const [copied, setCopied] = useState(false);
  if (!content) return null;
  return (
    <button
      type="button"
      onClick={() => {
        void navigator.clipboard?.writeText(content).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 1200);
        });
      }}
      title={t('common.open')}
      className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg text-muted-foreground hover:bg-white/[0.04] hover:text-foreground"
    >
      {copied ? <Check size={12} className="text-emerald-400" /> : <Copy size={12} />}
    </button>
  );
}

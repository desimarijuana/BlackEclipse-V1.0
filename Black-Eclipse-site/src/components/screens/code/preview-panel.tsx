'use client';

// ── PreviewPanel — run the project and look at it (Phase 24 / P2) ────────────
// One bounded operation over the existing execution layer. The panel never
// claims a URL the runtime did not confirm: "Running, but nothing is listening
// yet" is a real state, and the logs are one click away.

import { useCallback, useEffect, useRef, useState } from 'react';
import { ExternalLink, Loader2, Play, RefreshCw, Square, Terminal } from '@/lib/icons';
import { useT } from '@/lib/i18n/use-t';
import { cn } from '@/lib/utils';
import {
  getCodePreview,
  getCodePreviewLogs,
  startCodePreview,
  stopCodePreview,
  type CodePreview,
  type PreviewTarget,
} from '@/lib/harness/code-browser';

export interface PreviewPanelProps {
  taskId?: string | null;
  rootId?: string | null;
}

export function PreviewPanel({ taskId, rootId }: PreviewPanelProps) {
  const t = useT();
  const [preview, setPreview] = useState<CodePreview | null>(null);
  const [busy, setBusy] = useState<'start' | 'stop' | 'logs' | null>(null);
  const [logs, setLogs] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const target: PreviewTarget = taskId
    ? { taskId }
    : rootId ? { rootId } : {};

  const load = useCallback(async () => {
    try {
      setPreview(await getCodePreview(target));
      setError(null);
    } catch {
      // An idle preview is not an error; leave the last known state.
    }
  }, [taskId, rootId]);

  const prevTarget = useRef<PreviewTarget | null>(null);
  useEffect(() => {
    const previous = prevTarget.current;
    prevTarget.current = target;
    // Switching project stops the previous project's server: a preview is a
    // resource of the project that started it, not of the tab.
    if (previous && (previous.taskId !== target.taskId || previous.rootId !== target.rootId)) {
      void stopCodePreview(previous).catch(() => {});
    }
    setLogs(null);
    void load();
  }, [load]);

  const start = async () => {
    setBusy('start');
    setError(null);
    try {
      const next = await startCodePreview(target);
      setPreview(next);
      if (next.status === 'refused') setError(t('code.preview.refused'));
      if (next.status === 'failed') setError(next.reason || t('code.preview.failed'));
      if (next.status === 'unavailable') setError(t('code.preview.unavailable'));
    } catch {
      setError(t('code.preview.failed'));
    } finally {
      setBusy(null);
    }
  };

  const stop = async () => {
    setBusy('stop');
    try {
      setPreview(await stopCodePreview(target));
    } catch {
      setError(t('code.preview.failed'));
    } finally {
      setBusy(null);
    }
  };

  const restart = async () => {
    setBusy('start');
    setError(null);
    try {
      await stopCodePreview(target);
      const next = await startCodePreview(target);
      setPreview(next);
      if (next.status !== 'ok') setError(next.reason || t('code.preview.failed'));
    } catch {
      setError(t('code.preview.failed'));
    } finally {
      setBusy(null);
    }
  };

  const toggleLogs = async () => {
    if (logs !== null) { setLogs(null); return; }
    setBusy('logs');
    try {
      setLogs(await getCodePreviewLogs(target));
    } catch {
      setLogs('');
    } finally {
      setBusy(null);
    }
  };

  const running = Boolean(preview?.running);
  const ready = Boolean(preview?.ready && preview?.url);
  const plan = (preview?.plan ?? null) as { command?: string; source?: string } | null;
  const noCommand = preview?.status === 'idle' && plan?.source === 'none';

  return (
    <section className="glass-card-subtle rounded-xl border border-border/40 p-2.5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-[12px] font-medium text-foreground">{t('code.preview.title')}</p>
          <p className="text-[10.5px] text-muted-foreground/70">{t('code.preview.hint')}</p>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          {running ? (
            <>
              <button
                type="button"
                onClick={() => void restart()}
                disabled={busy != null}
                className="glass-button inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-[11px] text-muted-foreground disabled:opacity-50"
              >
                <RefreshCw size={11} />
                {t('code.preview.restart')}
              </button>
              <button
                type="button"
                onClick={() => void stop()}
                disabled={busy != null}
                className="glass-button inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-[11px] text-foreground disabled:opacity-50"
              >
                <Square size={11} />
                {t('code.preview.stop')}
              </button>
            </>
          ) : (
            <button
              type="button"
              onClick={() => void start()}
              disabled={busy != null || noCommand}
              className="glass-button inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-[11px] text-foreground disabled:opacity-50"
            >
              {busy === 'start' ? <Loader2 size={11} className="animate-spin" /> : <Play size={11} />}
              {busy === 'start' ? t('code.preview.starting') : t('code.preview.run')}
            </button>
          )}
          {running && !ready ? (
            <button
              type="button"
              onClick={() => void start()}
              disabled={busy != null}
              className="glass-button rounded-lg px-2.5 py-1 text-[11px] text-muted-foreground disabled:opacity-50"
            >
              {t('code.preview.checkAgain')}
            </button>
          ) : null}
          {(running || preview?.processState) ? (
            <button
              type="button"
              onClick={() => void toggleLogs()}
              disabled={busy != null}
              className="glass-button inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-[11px] text-muted-foreground disabled:opacity-50"
            >
              <Terminal size={11} />
              {logs === null ? t('code.preview.logs') : t('code.preview.hideLogs')}
            </button>
          ) : null}
        </div>
      </div>

      {error ? (
        <p className="mt-1.5 rounded-lg border border-amber-500/25 bg-amber-500/5 px-2 py-1 text-[10.5px] text-amber-300/90">
          {error}
        </p>
      ) : null}

      {!running && plan?.command ? (
        <p className="mt-1.5 text-[10.5px] text-muted-foreground/70">
          {t('code.preview.willRun', { command: plan.command })}
        </p>
      ) : null}

      {noCommand ? (
        <p className="mt-1.5 text-[10.5px] text-amber-300/90">{t('code.preview.refused')}</p>
      ) : null}

      {ready && preview?.url ? (
        <p className="mt-1.5 flex items-center gap-2 text-[12px]">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-400" />
          <a
            href={preview.url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex min-w-0 items-center gap-1 truncate text-primary underline-offset-2 hover:underline"
          >
            <span className="truncate">{preview.url}</span>
            <ExternalLink size={11} className="shrink-0" />
          </a>
          <span className="shrink-0 text-[10.5px] text-muted-foreground/60">{preview.command}</span>
        </p>
      ) : null}

      {running && !ready ? (
        <p className="mt-1.5 text-[11px] text-amber-300/90">{t('code.preview.notReady')}</p>
      ) : null}

      {!running && preview?.processState && preview.processState !== 'UNKNOWN' && !error ? (
        <p className="mt-1.5 text-[11px] text-muted-foreground/70">{t('code.preview.stopped')}</p>
      ) : null}

      {logs !== null ? (
        <pre className="mt-1.5 max-h-[200px] overflow-auto rounded-lg bg-background/60 p-2 text-[10.5px] leading-relaxed text-muted-foreground">
          {logs || t('code.preview.noLogs')}
        </pre>
      ) : null}
    </section>
  );
}

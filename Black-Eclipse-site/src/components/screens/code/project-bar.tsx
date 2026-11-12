'use client';

// ── ProjectBar — which project Builds works in ───────────────────────────────
// The Builds surface used to inherit "whatever folder is selected" invisibly.
// This makes the target explicit, reuses the ONE trusted-roots registry and the
// shared FolderPicker, and hands the id to the task list so a new build names
// its project instead of inferring it.
//
// The client only ever sends an approved root ID; the runtime resolves it.

import { useCallback, useEffect, useRef, useState } from 'react';
import { Check, ChevronDown, Folder, FolderOpen, Trash2 } from '@/lib/icons';
import { useT } from '@/lib/i18n/use-t';
import { cn } from '@/lib/utils';
import { listTrustedRoots, revokeTrustedRoot, selectTrustedRoot, type TrustedRoot } from '@/lib/harness/clients/code-browser';
import { FolderPicker } from '@/components/workspace/folder-picker';

/** The short name of a project folder (or the neutral default). */
export function folderLabel(path: string | null | undefined, label: string | null | undefined, fallback: string): string {
  if (label && label.trim()) return label.trim();
  if (!path) return fallback;
  const parts = path.replace(/\\/g, '/').split('/').filter(Boolean);
  return parts[parts.length - 1] ?? path;
}

export interface ProjectBarProps {
  /** The approved root new builds will use; null means the built-in default. */
  onChange?: (rootId: string | null) => void;
}

export function ProjectBar({ onChange }: ProjectBarProps) {
  const t = useT();
  const [roots, setRoots] = useState<TrustedRoot[]>([]);
  const [open, setOpen] = useState(false);
  const [picking, setPicking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    try {
      const next = await listTrustedRoots();
      setRoots(next);
      setError(false);
      onChange?.(next.find((root) => root.selected)?.id ?? null);
    } catch {
      setError(true);
    }
  }, [onChange]);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    if (!open) return;
    const onDown = (event: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const choose = useCallback(async (rootId: string | null) => {
    setBusy(true);
    try {
      const selected = await selectTrustedRoot(rootId);
      setOpen(false);
      onChange?.(selected?.id ?? null);
      await load();
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }, [load, onChange]);

  const remove = useCallback(async (rootId: string) => {
    setBusy(true);
    try {
      await revokeTrustedRoot(rootId);
      setOpen(false);
      await load();
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }, [load]);

  const current = roots.find((root) => root.selected) ?? null;
  const label = folderLabel(current?.path, current?.label, t('code.project.defaultName'));

  return (
    <div className="glass-card-subtle relative flex items-center justify-between gap-2 rounded-xl border border-border/40 px-2.5 py-1.5" ref={wrapRef}>
      <div className="min-w-0">
        <p className="text-[10px] uppercase tracking-wide text-muted-foreground/60">{t('code.project.label')}</p>
        <p className="flex items-center gap-1.5 truncate text-[12px] text-foreground" title={current?.path ?? ''}>
          {current ? <FolderOpen size={12} className="shrink-0" /> : <Folder size={12} className="shrink-0" />}
          <span className="truncate">{label}</span>
        </p>
      </div>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="menu"
        aria-expanded={open}
        disabled={busy}
        className="glass-button inline-flex shrink-0 items-center gap-1 rounded-lg px-2.5 py-1 text-[11px] text-foreground disabled:opacity-50"
      >
        {t('code.project.switch')}
        <ChevronDown size={11} className={cn('transition-transform', open && 'rotate-180')} />
      </button>

      {open ? (
        <div
          role="menu"
          aria-label={t('code.project.label')}
          className="glass-card-strong absolute right-0 top-full z-50 mt-1.5 w-[320px] overflow-hidden rounded-xl border border-border/40 p-1.5 text-[12px] shadow-xl"
        >
          {error ? (
            <p className="mx-1 my-1 rounded-lg border border-amber-500/25 bg-amber-500/5 px-2 py-1 text-[10.5px] text-amber-300/90">
              {t('code.project.failed')}
            </p>
          ) : null}

          {roots.length > 0 ? (
            <div className="max-h-[220px] overflow-y-auto py-0.5">
              {roots.map((root) => {
                const active = root.id === (current?.id ?? null);
                return (
                  <button
                    key={root.id}
                    type="button"
                    role="menuitemradio"
                    aria-checked={active}
                    disabled={busy}
                    onClick={() => void choose(root.id)}
                    className={cn(
                      'flex w-full items-start gap-2 rounded-lg px-2 py-1.5 text-left transition-colors hover:bg-white/5 disabled:opacity-50',
                      active && 'bg-white/[0.06]',
                    )}
                  >
                    <Folder size={14} className="mt-0.5 shrink-0 text-muted-foreground/70" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-foreground">{folderLabel(root.path, root.label, t('code.project.defaultName'))}</span>
                      <span className="block truncate text-[10px] text-muted-foreground/60" title={root.path}>{root.path}</span>
                    </span>
                    {active ? <Check size={13} className="mt-0.5 shrink-0 text-primary" /> : null}
                  </button>
                );
              })}
            </div>
          ) : (
            <p className="px-2 py-1.5 text-[11px] text-muted-foreground/70">{t('code.project.none')}</p>
          )}

          <div className="mt-0.5 border-t border-border/30 pt-0.5">
            <button
              type="button"
              onClick={() => { setOpen(false); setPicking(true); }}
              className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-foreground/90 transition-colors hover:bg-white/5"
            >
              <FolderOpen size={14} className="shrink-0 text-primary" />
              {t('code.project.openFolder')}
            </button>
            {current ? (
              <button
                type="button"
                disabled={busy}
                onClick={() => void choose(null)}
                className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-muted-foreground transition-colors hover:bg-white/5 hover:text-foreground disabled:opacity-50"
              >
                <Folder size={14} className="shrink-0" />
                {t('code.project.defaultOption')}
              </button>
            ) : null}
            {current ? (
              <button
                type="button"
                disabled={busy}
                onClick={() => void remove(current.id)}
                className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-rose-300/90 transition-colors hover:bg-white/5 disabled:opacity-50"
              >
                <Trash2 size={14} className="shrink-0" />
                {t('code.project.remove')}
              </button>
            ) : null}
          </div>
        </div>
      ) : null}

      {picking ? (
        <FolderPicker
          onClose={() => setPicking(false)}
          onApproved={() => { setPicking(false); void load(); }}
          selectGlobally
          approveLabel={t('code.project.useFolder')}
        />
      ) : null}
    </div>
  );
}

'use client';

// ── ProjectChip — this conversation's project folder ─────────────────────────
// The OpenCode-style "which folder am I working in" control, scoped to ONE chat.
// It reads/writes the server-side binding (`/api/chat/session/project`) and can
// approve a new folder with the shared picker. The client only ever sends an
// approved root ID — the runtime resolves it, so the browser cannot point a run
// at an arbitrary directory.

import { useCallback, useEffect, useRef, useState } from 'react';
import { Check, ChevronDown, Folder, FolderOpen } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { FolderPicker } from '@/components/workspace/folder-picker';

interface SessionProject {
  chatId: string;
  workspaceRootId: string | null;
  workspacePath: string | null;
  updatedAt: number;
}

interface Root {
  id: string;
  path: string;
  label?: string | null;
  selected?: boolean;
}

function folderName(path: string | null | undefined, label?: string | null): string {
  if (label && label.trim()) return label.trim();
  if (!path) return 'Eclipse repo';
  const parts = path.replace(/\\/g, '/').split('/').filter(Boolean);
  return parts[parts.length - 1] ?? path;
}

export function ProjectChip({ chatId, compact = false }: { chatId?: string; compact?: boolean }) {
  const [project, setProject] = useState<SessionProject | null>(null);
  const [roots, setRoots] = useState<Root[]>([]);
  const [runtime, setRuntime] = useState<'ready' | 'unavailable' | 'error'>('ready');
  const [open, setOpen] = useState(false);
  const [picking, setPicking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    if (!chatId) return;
    try {
      const res = await fetch(
        `/api/chat/session/project?chatId=${encodeURIComponent(chatId)}`,
        { cache: 'no-store' },
      );
      const data = (await res.json().catch(() => ({}))) as {
        project?: SessionProject | null;
        roots?: Root[];
        runtime?: 'ready' | 'unavailable' | 'error';
      };
      if (!res.ok) throw new Error('Could not read this chat’s folder');
      setProject(data.project ?? null);
      setRoots(Array.isArray(data.roots) ? data.roots : []);
      setRuntime(data.runtime ?? 'ready');
      setError(null);
    } catch {
      setRuntime('error');
    }
  }, [chatId]);

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

  const bind = useCallback(async (rootId: string | null) => {
    if (!chatId) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch('/api/chat/session/project', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chatId, rootId }),
      });
      const data = (await res.json().catch(() => ({}))) as {
        project?: SessionProject | null;
        error?: string;
      };
      if (!res.ok) throw new Error(data.error ?? 'Could not set the project folder');
      setProject(data.project ?? null);
      setOpen(false);
      void load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not set the project folder');
    } finally {
      setBusy(false);
    }
  }, [chatId, load]);

  if (!chatId) {
    return (
      <span
        className={cn(
          'inline-flex items-center gap-1.5 rounded-full border border-border/40 text-muted-foreground',
          compact ? 'px-2 py-0.5 text-[10px]' : 'px-2.5 py-1 text-[11px]',
        )}
        title="A project folder can be chosen once this chat exists."
      >
        <Folder size={12} /> Eclipse repo
      </span>
    );
  }

  const bound = project?.workspaceRootId ?? null;
  const activeRoot = bound ? roots.find((root) => root.id === bound) ?? null : null;
  const missing = Boolean(bound && !activeRoot);
  const label = missing
    ? 'Folder missing'
    : folderName(project?.workspacePath ?? activeRoot?.path, activeRoot?.label);

  return (
    <div className="relative min-w-0" ref={wrapRef}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="menu"
        aria-expanded={open}
        title={missing ? 'This chat’s folder is gone — choose another.' : project?.workspacePath ?? 'Eclipse repo (default)'}
        className={cn(
          'inline-flex max-w-[220px] items-center gap-1.5 rounded-full border border-border/40 bg-card/40 transition-colors hover:bg-accent hover:text-foreground',
          compact ? 'px-2 py-0.5 text-[10px]' : 'px-2.5 py-1 text-[11px]',
          missing ? 'text-amber-300' : 'text-muted-foreground',
        )}
      >
        {bound ? <FolderOpen size={12} className="shrink-0" /> : <Folder size={12} className="shrink-0" />}
        <span className="min-w-0 truncate">{label}</span>
        <ChevronDown size={11} className={cn('shrink-0 transition-transform', open && 'rotate-180')} />
      </button>

      {open ? (
        <div
          role="menu"
          aria-label="Project folder"
          className="glass-card-strong absolute bottom-full left-0 z-50 mb-2 w-[320px] overflow-hidden rounded-xl border border-border/40 p-1.5 text-[12px] shadow-xl"
        >
          <div className="px-2 pb-1 pt-1.5">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground/60">
              This chat works in
            </p>
            <p className="truncate text-[12px] font-medium text-foreground" title={project?.workspacePath ?? ''}>
              {missing ? 'Folder missing' : project?.workspacePath ?? 'Eclipse repo (default)'}
            </p>
          </div>

          {runtime !== 'ready' ? (
            <p className="mx-1 my-1 rounded-lg border border-amber-500/25 bg-amber-500/5 px-2 py-1 text-[10.5px] text-amber-300/90">
              {runtime === 'unavailable'
                ? 'The Eclipse runtime is not running, so folders cannot be listed.'
                : 'Could not read the approved folders just now.'}
            </p>
          ) : null}

          {roots.length > 0 ? (
            <div className="max-h-[220px] overflow-y-auto py-0.5">
              {roots.map((root) => {
                const current = root.id === bound;
                return (
                  <button
                    key={root.id}
                    type="button"
                    role="menuitemradio"
                    aria-checked={current}
                    disabled={busy}
                    onClick={() => void bind(root.id)}
                    className={cn(
                      'flex w-full items-start gap-2 rounded-lg px-2 py-1.5 text-left transition-colors hover:bg-white/5 disabled:opacity-50',
                      current && 'bg-white/[0.06]',
                    )}
                  >
                    <Folder size={14} className="mt-0.5 shrink-0 text-muted-foreground/70" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-foreground">{folderName(root.path, root.label)}</span>
                      <span className="block truncate text-[10px] text-muted-foreground/60" title={root.path}>
                        {root.path}
                      </span>
                    </span>
                    {current ? <Check size={13} className="mt-0.5 shrink-0 text-primary" /> : null}
                  </button>
                );
              })}
            </div>
          ) : (
            <p className="px-2 py-1.5 text-[11px] text-muted-foreground/70">No folders approved yet.</p>
          )}

          {error ? <p className="px-2 py-1 text-[10.5px] text-rose-300/90">{error}</p> : null}

          <div className="mt-0.5 border-t border-border/30 pt-0.5">
            <button
              type="button"
              onClick={() => { setOpen(false); setPicking(true); }}
              className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-foreground/90 transition-colors hover:bg-white/5"
            >
              <FolderOpen size={14} className="shrink-0 text-primary" />
              Open folder…
            </button>
            {bound ? (
              <button
                type="button"
                disabled={busy}
                onClick={() => void bind(null)}
                className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-muted-foreground transition-colors hover:bg-white/5 hover:text-foreground disabled:opacity-50"
              >
                <Folder size={14} className="shrink-0" />
                Use Eclipse repo (default)
              </button>
            ) : null}
          </div>
        </div>
      ) : null}

      {picking ? (
        <FolderPicker
          onClose={() => setPicking(false)}
          onApproved={(root) => { setPicking(false); void bind(root.id); }}
          approveLabel="Use this folder"
        />
      ) : null}
    </div>
  );
}

export default ProjectChip;

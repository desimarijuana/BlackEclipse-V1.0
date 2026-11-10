'use client';

// ── ProjectChip — this conversation's project folder ─────────────────────────
// The OpenCode-style "which folder am I working in" control, scoped to ONE chat.
// It reads/writes the server-side binding (`/api/chat/session/project`) and can
// approve a new folder with the shared picker. The client only ever sends an
// approved root ID — the runtime resolves it, so the browser cannot point a run
// at an arbitrary directory.
//
// The chip always shows the folder it would use, even before a chat exists:
// with no binding it displays the server-resolved DEFAULT root path, so the
// operator can see where work will happen instead of a bare "Eclipse repo"
// label. A folder chosen before the chat id exists is remembered locally and
// bound as soon as the first message creates the conversation.

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

interface PendingRoot {
  rootId: string;
  path: string;
}

/** A folder picked before the chat exists; bound when the chat id appears. */
const PENDING_KEY = 'eclipse.pendingProjectRoot';

function readPending(): PendingRoot | null {
  if (typeof window === 'undefined') return null;
  try {
    const parsed = JSON.parse(window.localStorage.getItem(PENDING_KEY) || 'null') as Partial<PendingRoot> | null;
    if (!parsed || typeof parsed.rootId !== 'string' || typeof parsed.path !== 'string') return null;
    return { rootId: parsed.rootId, path: parsed.path };
  } catch {
    return null;
  }
}

function writePending(value: PendingRoot | null): void {
  if (typeof window === 'undefined') return;
  try {
    if (value) window.localStorage.setItem(PENDING_KEY, JSON.stringify(value));
    else window.localStorage.removeItem(PENDING_KEY);
  } catch {
    /* storage unavailable — the choice simply stays in memory */
  }
}

function folderName(path: string | null | undefined): string {
  if (!path) return 'Eclipse repo';
  const parts = path.replace(/\\/g, '/').split('/').filter(Boolean);
  return parts[parts.length - 1] ?? path;
}

export function ProjectChip({ chatId, compact = false }: { chatId?: string; compact?: boolean }) {
  const [project, setProject] = useState<SessionProject | null>(null);
  const [projectLoaded, setProjectLoaded] = useState(false);
  const [roots, setRoots] = useState<Root[]>([]);
  const [defaultRoot, setDefaultRoot] = useState<string | null>(null);
  const [runtime, setRuntime] = useState<'ready' | 'unavailable' | 'error'>('ready');
  const [pending, setPending] = useState<PendingRoot | null>(null);
  const [open, setOpen] = useState(false);
  const [picking, setPicking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const pendingAppliedRef = useRef(false);

  const load = useCallback(async () => {
    setProjectLoaded(false);
    setPending(readPending());
    try {
      // Without a chat id only the workspace context (roots + default folder)
      // is needed — the default path is what the chip shows until a chat exists.
      const url = chatId
        ? `/api/chat/session/project?chatId=${encodeURIComponent(chatId)}`
        : '/api/workspace/roots';
      const res = await fetch(url, { cache: 'no-store' });
      const data = (await res.json().catch(() => ({}))) as {
        project?: SessionProject | null;
        roots?: Root[];
        defaultRoot?: string | null;
        runtime?: 'ready' | 'unavailable' | 'error';
      };
      if (!res.ok) throw new Error('Could not read this chat’s folder');
      setProject(data.project ?? null);
      setRoots(Array.isArray(data.roots) ? data.roots : []);
      setDefaultRoot(typeof data.defaultRoot === 'string' ? data.defaultRoot : null);
      setRuntime(data.runtime ?? 'ready');
      setError(null);
    } catch {
      setRuntime('error');
    } finally {
      setProjectLoaded(true);
    }
  }, [chatId]);

  useEffect(() => {
    pendingAppliedRef.current = false;
    void load();
  }, [load]);

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
      writePending(null);
      setPending(null);
      setOpen(false);
      void load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not set the project folder');
    } finally {
      setBusy(false);
    }
  }, [chatId, load]);

  // A folder chosen before the chat existed is bound as soon as the chat id
  // arrives (the first message creates the conversation).
  useEffect(() => {
    if (!chatId || !projectLoaded || pendingAppliedRef.current) return;
    const queued = readPending();
    if (!queued) return;
    pendingAppliedRef.current = true;
    if (project?.workspaceRootId) {
      // Already bound to something else — never override a real binding.
      writePending(null);
      setPending(null);
      return;
    }
    void bind(queued.rootId);
  }, [chatId, projectLoaded, project?.workspaceRootId, bind]);

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

  const choose = useCallback((root: PendingRoot) => {
    if (!chatId) {
      const value = { rootId: root.rootId, path: root.path };
      writePending(value);
      setPending(value);
      setOpen(false);
      setError(null);
      return;
    }
    void bind(root.rootId);
  }, [chatId, bind]);

  const useDefault = useCallback(() => {
    if (!chatId) {
      writePending(null);
      setPending(null);
      setOpen(false);
      setError(null);
      return;
    }
    void bind(null);
  }, [chatId, bind]);

  const boundRootId = project?.workspaceRootId ?? pending?.rootId ?? null;
  const boundPath = project?.workspacePath ?? pending?.path ?? null;
  const activeRoot = boundRootId ? roots.find((root) => root.id === boundRootId) ?? null : null;
  // A real binding whose root was revoked is surfaced honestly. A pending
  // choice is not "missing" just because the folder list has not arrived yet.
  const missing = Boolean(project?.workspaceRootId && !activeRoot);
  const effectivePath = missing ? null : boundPath ?? activeRoot?.path ?? defaultRoot;
  const label = missing
    ? 'Folder missing'
    : activeRoot?.label?.trim() || folderName(effectivePath);

  return (
    <div className="relative min-w-0" ref={wrapRef}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="menu"
        aria-expanded={open}
        title={missing ? 'This chat’s folder is gone — choose another.' : effectivePath ?? 'Choose a project folder'}
        className={cn(
          'inline-flex min-w-0 items-center gap-1.5 rounded-full border border-border/40 bg-card/40 transition-colors hover:bg-accent hover:text-foreground',
          compact ? 'max-w-[240px] px-2 py-0.5 text-[10px]' : 'max-w-[360px] px-2.5 py-1 text-[11px]',
          missing ? 'text-amber-300' : 'text-muted-foreground',
        )}
      >
        {boundRootId ? <FolderOpen size={12} className="shrink-0" /> : <Folder size={12} className="shrink-0" />}
        <span className="min-w-0 shrink-0 font-medium">{label}</span>
        {effectivePath ? (
          <span
            className={cn(
              'min-w-0 truncate font-mono text-muted-foreground/60',
              compact ? 'text-[9.5px]' : 'text-[10px]',
            )}
          >
            {effectivePath}
          </span>
        ) : null}
        <ChevronDown size={11} className={cn('shrink-0 transition-transform', open && 'rotate-180')} />
      </button>

      {open ? (
        <div
          role="menu"
          aria-label="Project folder"
          className="glass-card-strong absolute bottom-full left-0 z-[150] mb-2 w-[340px] overflow-hidden rounded-xl border border-border/40 p-1.5 text-[12px] shadow-xl"
        >
          <div className="px-2 pb-1 pt-1.5">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground/60">
              {chatId ? 'This chat works in' : 'Workspace folder'}
            </p>
            <p
              className="break-all font-mono text-[11px] font-medium leading-snug text-foreground"
              title={effectivePath ?? ''}
            >
              {missing ? 'Folder missing' : effectivePath ?? 'Eclipse repo (default)'}
            </p>
            {!chatId && pending ? (
              <p className="mt-1 text-[10px] text-primary/80">
                Chosen for your next chat — it binds when the conversation starts.
              </p>
            ) : null}
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
                const current = root.id === boundRootId;
                return (
                  <button
                    key={root.id}
                    type="button"
                    role="menuitemradio"
                    aria-checked={current}
                    disabled={busy}
                    onClick={() => choose({ rootId: root.id, path: root.path })}
                    className={cn(
                      'flex w-full items-start gap-2 rounded-lg px-2 py-1.5 text-left transition-colors hover:bg-white/5 disabled:opacity-50',
                      current && 'bg-white/[0.06]',
                    )}
                  >
                    <Folder size={14} className="mt-0.5 shrink-0 text-muted-foreground/70" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-foreground">{folderName(root.path)}</span>
                      <span className="block break-all font-mono text-[10px] leading-snug text-muted-foreground/60" title={root.path}>
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
            <button
              type="button"
              disabled={busy}
              onClick={useDefault}
              className={cn(
                'flex w-full items-start gap-2 rounded-lg px-2 py-1.5 text-left transition-colors hover:bg-white/5 disabled:opacity-50',
                boundRootId ? 'text-muted-foreground hover:text-foreground' : 'bg-white/[0.06] text-foreground',
              )}
            >
              <Folder size={14} className="mt-0.5 shrink-0" />
              <span className="min-w-0 flex-1">
                <span className="block">Use Eclipse repo (default)</span>
                {defaultRoot ? (
                  <span className="block break-all font-mono text-[10px] leading-snug text-muted-foreground/60" title={defaultRoot}>
                    {defaultRoot}
                  </span>
                ) : null}
              </span>
              {!boundRootId ? <Check size={13} className="mt-0.5 shrink-0 text-primary" /> : null}
            </button>
          </div>
        </div>
      ) : null}

      {picking ? (
        <FolderPicker
          onClose={() => setPicking(false)}
          onApproved={(root) => {
            setPicking(false);
            choose({ rootId: root.id, path: root.path });
          }}
          approveLabel="Use this folder"
        />
      ) : null}
    </div>
  );
}

export default ProjectChip;

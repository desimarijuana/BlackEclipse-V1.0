'use client';

// ── Folder picker (shared) ─────────────────────────────────────────────────────
// A modal that browses the filesystem and approves one folder as a workspace
// root. Reused by the Editor screen and the chat project chip.
//
// It is portaled to <body> and sits above every app surface (z-200): rendered
// inline it could be clipped or stacked under the sidebar. The in-app browser is
// Node-native (`browse-server.ts`) so a Python runtime restart never freezes it,
// and on Windows a button opens the REAL OS "Select Folder" dialog.
//
// Accessibility: role=dialog + aria-modal, a labelled title, initial focus,
// Escape to close, and a Tab focus trap. Approving a folder is the one
// widening action; it still goes through the runtime's trusted-root store.

import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useT } from '@/lib/i18n/use-t';
import { Check, ChevronRight, Folder, FolderOpen, Loader2, Plus, X } from '@/lib/icons';
import {
  approveTrustedRoot,
  browseFolders,
  createBrowsedFolder,
  listTrustedRoots,
  pickFolderNative,
  selectTrustedRoot,
  type BrowseEntry,
  type TrustedRoot,
} from '@/lib/harness/clients/code-browser';

const RECENT_KEY = 'eclipse.folderPicker.recent';
const MAX_RECENT = 6;

function readRecents(): string[] {
  try {
    const raw = window.localStorage.getItem(RECENT_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((p): p is string => typeof p === 'string') : [];
  } catch {
    return [];
  }
}

function rememberRecent(path: string): string[] {
  const next = [path, ...readRecents().filter((p) => p !== path)].slice(0, MAX_RECENT);
  try { window.localStorage.setItem(RECENT_KEY, JSON.stringify(next)); } catch { /* storage unavailable */ }
  return next;
}

/** Absolute path breadcrumb, preserving the drive/root segment. */
function pathSegments(path: string | null): Array<{ label: string; path: string }> {
  if (!path) return [];
  const normalized = path.replace(/\\/g, '/');
  const drive = /^([A-Za-z]:)(\/|$)/.exec(normalized);
  const parts = normalized.split('/').filter(Boolean);
  const out: Array<{ label: string; path: string }> = [];
  if (drive) {
    // Windows: `C:` then each folder beneath it.
    let acc = `${drive[1]}/`;
    out.push({ label: drive[1], path: acc });
    for (const part of parts.slice(1)) {
      acc = acc.endsWith('/') ? `${acc}${part}` : `${acc}/${part}`;
      out.push({ label: part, path: acc });
    }
    return out;
  }
  let acc = '';
  for (const part of parts) {
    acc = `${acc}/${part}`;
    out.push({ label: part, path: acc });
  }
  return out;
}

export interface FolderPickerProps {
  onClose: () => void;
  /** Called after approval (and optional global selection). */
  onApproved: (root: TrustedRoot) => void;
  /**
   * Also make the approved folder the GLOBAL selection. The Editor screen wants
   * this; a per-chat project does not — it binds the root to that chat only.
   */
  selectGlobally?: boolean;
  approveLabel?: string;
}

/** A cancelled/timed-out browse must say what happened, not spin forever. */
function browseErrorMessage(err: unknown, fallback: string): string {
  const name = err instanceof Error ? err.name : '';
  if (name === 'TimeoutError' || name === 'AbortError') {
    return 'The folder list took too long to load. Check that the runtime is running, then try again.';
  }
  return err instanceof Error && err.message ? err.message : fallback;
}

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function FolderPicker({
  onClose,
  onApproved,
  selectGlobally = false,
  approveLabel,
}: FolderPickerProps) {
  const t = useT();
  const [mounted, setMounted] = useState(false);
  const [path, setPath] = useState<string | null>(null);
  const [pathInput, setPathInput] = useState('');
  const [entries, setEntries] = useState<BrowseEntry[]>([]);
  const [parent, setParent] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showNew, setShowNew] = useState(false);
  const [newName, setNewName] = useState('');
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [created, setCreated] = useState<string | null>(null);
  const [nativeBusy, setNativeBusy] = useState(false);
  const [nativeNote, setNativeNote] = useState<string | null>(null);
  const firstLoad = useRef(false);
  const dialogRef = useRef<HTMLDivElement>(null);
  const isWindows = typeof navigator !== 'undefined' && /Windows/i.test(navigator.userAgent);
  const [roots, setRoots] = useState<TrustedRoot[]>([]);
  const [recent, setRecent] = useState<string[]>([]);

  useEffect(() => { setMounted(true); }, []);

  // Approved roots + recent folders are the picker's "where am I" rail. Both are
  // best-effort: a runtime/storage failure simply leaves the rail empty.
  useEffect(() => {
    setRecent(readRecents());
    void listTrustedRoots().then(setRoots).catch(() => setRoots([]));
  }, []);

  const load = useCallback(async (target?: string) => {
    setBusy(true);
    setError(null);
    setCreated(null);
    try {
      const result = await browseFolders(target);
      setPath(result.path);
      setPathInput(result.path ?? '');
      setEntries(result.entries);
      setParent(result.parent);
      setError(result.reason);
    } catch (err) {
      setError(browseErrorMessage(err, t('editor.listFailed')));
    } finally {
      setBusy(false);
    }
  }, [t]);

  useEffect(() => {
    // StrictMode mounts the effect twice in dev; fire ONE browse call so two
    // concurrent listings cannot contend for the same short-lived connection.
    if (firstLoad.current) return;
    firstLoad.current = true;
    void load(undefined);
  }, [load]);

  // Focus + Escape + a Tab trap, then restore focus to the opener on close.
  // `onClose` may be a new function each render; keep the latest in a ref so the
  // focus effect runs ONCE (otherwise every keystroke would re-focus the dialog).
  const onCloseRef = useRef(onClose);
  useEffect(() => { onCloseRef.current = onClose; }, [onClose]);

  useEffect(() => {
    const el = dialogRef.current;
    if (!el) return;
    const previous = document.activeElement as HTMLElement | null;
    const items = () => Array.from(el.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((node) => node.offsetParent !== null);
    const pathField = el.querySelector<HTMLInputElement>('input[aria-label="Folder path"]');
    (pathField ?? items()[0])?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== 'Tab') return;
      const list = items();
      if (list.length === 0) return;
      const first = list[0];
      const last = list[list.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      previous?.focus?.();
    };
  }, [mounted]);

  const approve = useCallback(async () => {
    if (!path) return;
    setBusy(true);
    try {
      const root = await approveTrustedRoot(path);
      setRecent(rememberRecent(path));
      setRoots((prev) => (prev.some((r) => r.id === root.id) ? prev : [...prev, root]));
      if (selectGlobally) await selectTrustedRoot(root.id);
      onApproved(root);
    } catch (err) {
      setError(browseErrorMessage(err, t('editor.listFailed')));
      setBusy(false);
    }
  }, [path, onApproved, selectGlobally, t]);

  const go = useCallback(() => {
    const target = pathInput.trim();
    void load(target || undefined);
  }, [pathInput, load]);

  const create = useCallback(async () => {
    const name = newName.trim();
    if (!path || !name) return;
    setCreating(true);
    setCreateError(null);
    setCreated(null);
    try {
      const folder = await createBrowsedFolder(path, name);
      setNewName('');
      setShowNew(false);
      setCreated(`Created “${folder.name}”`);
      await load(folder.path);
      setCreated(`Created “${folder.name}”`);
    } catch (err) {
      setCreateError(err instanceof Error && err.message ? err.message : 'That folder could not be created.');
    } finally {
      setCreating(false);
    }
  }, [newName, path, load]);

  const openWindows = useCallback(async () => {
    if (nativeBusy) return;
    setNativeBusy(true);
    setNativeNote('Waiting for the Windows folder window…');
    setCreateError(null);
    try {
      const chosen = await pickFolderNative();
      if (chosen) await load(chosen);
      setNativeNote(null);
    } catch (err) {
      setNativeNote(null);
      setCreateError(err instanceof Error ? err.message : 'The Windows folder window could not open.');
    } finally {
      setNativeBusy(false);
    }
  }, [nativeBusy, load]);

  const folders = entries.filter((entry) => entry.isDir);

  const dialog = (
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center bg-black/60 p-3 backdrop-blur-sm sm:p-6"
      onClick={onClose}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="folder-picker-title"
        className="glass-card-strong flex max-h-[82vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-border/40 shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start gap-3 border-b border-border/30 px-4 py-3">
          <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-primary/15 text-primary">
            <FolderOpen size={18} />
          </span>
          <div className="min-w-0 flex-1">
            <h2 id="folder-picker-title" className="text-[15px] font-semibold text-foreground">
              {t('editor.chooseFolder')}
            </h2>
            <p className="mt-0.5 text-[11.5px] text-muted-foreground">
              Pick a folder on this computer, or create a new one.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close folder picker"
            className="shrink-0 rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50"
          >
            <X size={16} />
          </button>
        </div>

        {/* Navigation */}
        <div className="flex flex-wrap items-center gap-1.5 border-b border-border/30 px-4 py-2">
          <button
            type="button"
            disabled={!parent || busy}
            onClick={() => parent && void load(parent)}
            aria-label={t('editor.up')}
            className="inline-flex h-8 items-center gap-1 rounded-lg px-2 text-[11.5px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:opacity-30"
          >
            ↑ <span className="hidden sm:inline">{t('editor.up')}</span>
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => void load(undefined)}
            className="inline-flex h-8 items-center rounded-lg px-2 text-[11.5px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:opacity-30"
            title="Show the drives / filesystem roots"
          >
            Drives
          </button>
          <div className="flex min-w-[200px] flex-1 items-center gap-1.5">
            <input
              value={pathInput}
              onChange={(event) => setPathInput(event.target.value)}
              onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); go(); } }}
              spellCheck={false}
              placeholder="Type or paste a folder path…"
              aria-label="Folder path"
              className="h-8 min-w-0 flex-1 rounded-lg border border-border/40 bg-black/20 px-2.5 font-mono text-[11.5px] text-foreground outline-none placeholder:text-muted-foreground/50 focus:border-primary focus-visible:ring-2 focus-visible:ring-primary/30"
              title={path ?? 'Filesystem roots'}
            />
            <button
              type="button"
              disabled={busy}
              onClick={go}
              className="inline-flex h-8 shrink-0 items-center rounded-lg px-2.5 text-[11.5px] font-medium text-primary transition-colors hover:bg-primary/10 disabled:opacity-40"
            >
              Go
            </button>
          </div>
          {isWindows && (
            <button
              type="button"
              disabled={nativeBusy || busy}
              onClick={() => void openWindows()}
              className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-lg border border-border/40 px-2.5 text-[11.5px] text-foreground transition-colors hover:bg-accent disabled:opacity-40"
              title="Open the Windows Select Folder window"
            >
              {nativeBusy ? <Loader2 size={13} className="animate-spin" /> : <FolderOpen size={13} />}
              Windows…
            </button>
          )}
        </div>

        {/* Where am I: approved roots, a clickable absolute breadcrumb, recents. */}
        <div className="space-y-1 border-b border-border/30 px-4 py-2">
          {roots.length > 0 && (
            <div className="flex flex-wrap items-center gap-1">
              <span className="mr-1 text-[9.5px] uppercase tracking-wide text-muted-foreground/50">Approved</span>
              {roots.map((root) => (
                <button
                  key={root.id}
                  type="button"
                  onClick={() => void load(root.path)}
                  title={root.path}
                  className="inline-flex max-w-[180px] items-center gap-1 rounded-full border border-border/40 px-2 py-0.5 text-[10.5px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                >
                  <Folder size={10} className="shrink-0" />
                  <span className="truncate">{root.label?.trim() || root.path}</span>
                  {root.selected && <Check size={9} className="shrink-0 text-primary" />}
                </button>
              ))}
            </div>
          )}
          <div className="flex min-w-0 flex-wrap items-center gap-0.5 text-[11px]">
            {pathSegments(path).map((segment, index, all) => (
              <span key={segment.path} className="flex min-w-0 items-center gap-0.5">
                {index > 0 && <ChevronRight size={10} className="shrink-0 text-muted-foreground/30" />}
                <button
                  type="button"
                  onClick={() => void load(segment.path)}
                  className="max-w-[150px] truncate rounded px-1 py-0.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                  title={segment.path}
                >
                  {segment.label}
                </button>
                {index === all.length - 1 && <span className="text-[9.5px] text-primary/70">here</span>}
              </span>
            ))}
            {!path && <span className="text-muted-foreground/50">Filesystem roots</span>}
          </div>
          {recent.length > 0 && (
            <div className="flex flex-wrap items-center gap-1">
              <span className="mr-1 text-[9.5px] uppercase tracking-wide text-muted-foreground/50">Recent</span>
              {recent.map((entry) => (
                <button
                  key={entry}
                  type="button"
                  onClick={() => void load(entry)}
                  title={entry}
                  className="max-w-[150px] truncate rounded px-1.5 py-0.5 text-[10.5px] text-muted-foreground/80 transition-colors hover:bg-accent hover:text-foreground"
                >
                  {entry.replace(/\\/g, '/').split('/').filter(Boolean).pop() ?? entry}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* New folder */}
        <div className="border-b border-border/30 px-4 py-2">
          {showNew ? (
            <div className="flex items-center gap-1.5">
              <input
                value={newName}
                onChange={(event) => setNewName(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') { event.preventDefault(); void create(); }
                  if (event.key === 'Escape') { event.preventDefault(); setShowNew(false); setNewName(''); }
                }}
                placeholder="New folder name"
                aria-label="New folder name"
                autoFocus
                className="h-8 min-w-0 flex-1 rounded-lg border border-border/40 bg-black/20 px-2.5 text-[11.5px] text-foreground outline-none placeholder:text-muted-foreground/50 focus:border-primary focus-visible:ring-2 focus-visible:ring-primary/30"
              />
              <button
                type="button"
                disabled={!newName.trim() || !path || creating}
                onClick={() => void create()}
                className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-lg bg-primary/90 px-3 text-[11.5px] font-medium text-primary-foreground transition-colors hover:bg-primary disabled:opacity-40"
              >
                {creating && <Loader2 size={12} className="animate-spin" />}
                {creating ? 'Creating…' : 'Create'}
              </button>
              <button
                type="button"
                onClick={() => { setShowNew(false); setNewName(''); setCreateError(null); }}
                className="inline-flex h-8 shrink-0 items-center rounded-lg px-2.5 text-[11.5px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                Cancel
              </button>
            </div>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                disabled={!path || busy}
                onClick={() => { setShowNew(true); setCreateError(null); setCreated(null); }}
                className="inline-flex h-8 items-center gap-1.5 rounded-lg px-2 text-[11.5px] font-medium text-foreground/90 transition-colors hover:bg-accent disabled:opacity-30"
                title={path ? 'Create a folder here' : 'Choose a drive first'}
              >
                <Plus size={13} /> New folder
              </button>
              {nativeNote && <span className="text-[10.5px] text-muted-foreground/80">{nativeNote}</span>}
              {created && !createError && (
                <span className="inline-flex items-center gap-1 text-[10.5px] text-primary/90"><Check size={11} /> {created}</span>
              )}
            </div>
          )}
          {createError && <p className="mt-1.5 text-[10.5px] text-amber-300/90" role="alert">{createError}</p>}
        </div>

        {/* Folder list */}
        <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2" aria-live="polite">
          {busy && folders.length === 0 && (
            <div className="flex items-center justify-center gap-2 py-10 text-[12px] text-muted-foreground">
              <Loader2 size={15} className="animate-spin" /> Reading folder…
            </div>
          )}
          {!busy && error && (
            <div className="mx-2 my-2 flex items-start gap-2 rounded-xl border border-amber-500/25 bg-amber-500/5 p-2.5">
              <p className="min-w-0 flex-1 text-[11.5px] text-amber-300/90">{error}</p>
              <button
                type="button"
                onClick={() => void load(path ?? undefined)}
                className="shrink-0 rounded-lg px-2 py-1 text-[11px] font-medium text-primary transition-colors hover:bg-primary/10"
              >
                Retry
              </button>
            </div>
          )}
          {!busy && !error && folders.length === 0 && (
            <p className="px-3 py-8 text-center text-[12px] text-muted-foreground/70">
              No folders inside this one. You can create one above.
            </p>
          )}
          <div className="space-y-0.5">
            {folders.map((entry) => (
              <button
                key={entry.path}
                type="button"
                onClick={() => void load(entry.path)}
                className="group flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left transition-colors hover:bg-accent focus-visible:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
              >
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-accent/40 text-muted-foreground/80 group-hover:text-foreground">
                  <Folder size={15} />
                </span>
                <span className="min-w-0 flex-1 truncate text-[12.5px] text-foreground/90">{entry.name}</span>
                <ChevronRight size={14} className="shrink-0 text-muted-foreground/40 group-hover:text-muted-foreground" />
              </button>
            ))}
          </div>
        </div>

        {/* Footer */}
        <div className="flex flex-wrap items-center gap-2 border-t border-border/30 px-4 py-2.5">
          <span className="min-w-0 flex-1 truncate font-mono text-[10.5px] text-muted-foreground/70" title={path ?? ''}>
            {path ?? 'Filesystem roots'}
          </span>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-8 items-center rounded-lg px-3 text-[12px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            {t('editor.cancel')}
          </button>
          <button
            type="button"
            disabled={!path || busy}
            onClick={() => void approve()}
            className="inline-flex h-8 items-center rounded-lg bg-primary px-3.5 text-[12px] font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-40"
          >
            {approveLabel ?? t('editor.approve')}
          </button>
        </div>
      </div>
    </div>
  );

  if (!mounted) return null;
  return createPortal(dialog, document.body);
}

export default FolderPicker;

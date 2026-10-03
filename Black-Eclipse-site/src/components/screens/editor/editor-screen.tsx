'use client';

// ── Editor — file tree + text editor over the selected workspace folder ──────
// The client side of the folder picker + editor. It talks ONLY to the client-safe
// code-browser (which calls the Next.js /api/workspace routes); it holds no
// filesystem logic. Reading, writing and listing are all confined to the selected
// folder by the runtime — the same confinement the agent tools use — so this is a
// second door to the SAME boundary, never a weaker one.
//
// A minimal, dependency-free editor: a directory tree, a monospace textarea, and
// a Save that writes the file. Syntax highlighting is deliberately not bundled
// (no Monaco/CodeMirror dependency added) — this is the working core.

import { useCallback, useEffect, useState } from 'react';
import { useT } from '@/lib/i18n/use-t';
import { cn } from '@/lib/utils';
import {
  approveTrustedRoot,
  browseFolders,
  listTrustedRoots,
  listWorkspaceFiles,
  readWorkspaceFile,
  selectTrustedRoot,
  writeWorkspaceFile,
  type BrowseEntry,
  type EditorEntry,
  type TrustedRoot,
} from '@/lib/harness/code-browser';

export function EditorScreen() {
  const t = useT();
  const [roots, setRoots] = useState<TrustedRoot[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [picking, setPicking] = useState(false);

  const refreshRoots = useCallback(async () => {
    try {
      setRoots(await listTrustedRoots());
      setError(null);
    } catch {
      setError(t('editor.listFailed'));
    }
  }, [t]);

  useEffect(() => { void refreshRoots(); }, [refreshRoots]);

  const selected = roots.find((r) => r.selected) ?? null;

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 p-4">
      <header className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <h2 className="text-[15px] font-medium text-foreground">{t('editor.heading')}</h2>
          {selected && (
            <p className="truncate text-[11px] text-muted-foreground" title={selected.path}>
              {t('editor.currentFolder')}: <span className="text-foreground/90">{selected.path}</span>
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={() => setPicking(true)}
          className="glass-button shrink-0 rounded-lg px-3 py-1.5 text-[12px] text-foreground"
        >
          {t('editor.openFolder')}
        </button>
      </header>

      {error && (
        <div className="glass-card-subtle rounded-xl border border-red-500/30 p-2.5 text-[12px] text-red-300">
          {error}
        </div>
      )}

      {!selected ? (
        <div className="glass-card-subtle rounded-xl p-4 text-[13px] text-muted-foreground">
          {t('editor.noFolder')}
        </div>
      ) : (
        <FileWorkspace key={selected.id} root={selected} />
      )}

      {picking && (
        <FolderPicker
          onClose={() => setPicking(false)}
          onPicked={() => { setPicking(false); void refreshRoots(); }}
        />
      )}
    </div>
  );
}

// ── The tree + editor ────────────────────────────────────────────────────────

function FileWorkspace({ root }: { root: TrustedRoot }) {
  const t = useT();
  const [entries, setEntries] = useState<EditorEntry[]>([]);
  const [path, setPath] = useState('.');
  const [openFile, setOpenFile] = useState<string | null>(null);
  const [content, setContent] = useState('');
  const [original, setOriginal] = useState('');
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const loadDir = useCallback(async (dir: string) => {
    try {
      const result = await listWorkspaceFiles(dir);
      setEntries(result.entries);
      setPath(result.path || '.');
      setStatus(null);
    } catch {
      setStatus(t('editor.listFailed'));
    }
  }, [t]);

  useEffect(() => { void loadDir('.'); }, [loadDir, root.id]);

  const open = useCallback(async (file: string) => {
    try {
      const result = await readWorkspaceFile(file);
      setOpenFile(result.path);
      setContent(result.content);
      setOriginal(result.content);
      setStatus(result.redacted ? t('editor.redacted') : null);
    } catch (err) {
      setStatus(err instanceof Error ? err.message : t('editor.readFailed'));
    }
  }, [t]);

  const save = useCallback(async () => {
    if (!openFile) return;
    setBusy(true);
    try {
      await writeWorkspaceFile(openFile, content);
      setOriginal(content);
      setStatus(t('editor.saved'));
    } catch (err) {
      setStatus(err instanceof Error ? err.message : t('editor.saveFailed'));
    } finally {
      setBusy(false);
    }
  }, [openFile, content, t]);

  const dirty = content !== original;
  const parent = path !== '.' && path !== '' ? path.split('/').slice(0, -1).join('/') || '.' : null;

  return (
    <div className="grid min-h-0 flex-1 gap-3 lg:grid-cols-[260px_1fr]">
      <div className="glass-card flex min-h-0 flex-col overflow-hidden">
        <div className="flex items-center justify-between gap-2 border-b border-white/5 px-2.5 py-1.5">
          <span className="text-[11px] font-medium text-muted-foreground">{t('editor.files')}</span>
          {parent && (
            <button
              type="button"
              onClick={() => void loadDir(parent)}
              className="rounded px-1.5 py-0.5 text-[11px] text-muted-foreground hover:text-foreground"
            >
              ↑ {t('editor.up')}
            </button>
          )}
        </div>
        <div className="min-h-0 flex-1 overflow-auto p-1">
          {entries.length === 0 && (
            <p className="p-2 text-[11px] text-muted-foreground">{t('editor.emptyFolder')}</p>
          )}
          {entries.map((entry) => (
            <button
              key={entry.path}
              type="button"
              onClick={() => (entry.isDir ? void loadDir(entry.path) : void open(entry.path))}
              className={cn(
                'flex w-full items-center gap-1.5 rounded px-2 py-1 text-left text-[12px] transition-colors hover:bg-white/5',
                !entry.isDir && openFile === entry.path ? 'bg-primary/15 text-foreground' : 'text-foreground/80',
              )}
            >
              <span className="w-3 shrink-0 text-[10px] text-muted-foreground">{entry.isDir ? '▸' : '·'}</span>
              <span className="truncate">{entry.name}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="glass-card flex min-h-0 flex-col overflow-hidden">
        {openFile ? (
          <>
            <div className="flex items-center justify-between gap-2 border-b border-white/5 px-2.5 py-1.5">
              <span className="truncate text-[11px] text-foreground/90">{openFile}{dirty ? ' •' : ''}</span>
              <div className="flex shrink-0 gap-1.5">
                {dirty && (
                  <button
                    type="button"
                    onClick={() => setContent(original)}
                    className="rounded px-2 py-0.5 text-[11px] text-muted-foreground hover:text-foreground"
                  >
                    {t('editor.revert')}
                  </button>
                )}
                <button
                  type="button"
                  disabled={busy || !dirty}
                  onClick={() => void save()}
                  className="glass-button rounded-lg px-2.5 py-1 text-[11px] text-foreground disabled:opacity-40"
                >
                  {busy ? t('editor.saving') : t('editor.save')}
                </button>
              </div>
            </div>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              spellCheck={false}
              className="min-h-0 flex-1 resize-none bg-transparent p-3 font-mono text-[12px] leading-5 text-foreground outline-none"
            />
          </>
        ) : (
          <div className="flex flex-1 items-center justify-center p-4 text-[12px] text-muted-foreground">
            {t('editor.selectFile')}
          </div>
        )}
        {status && (
          <div className="border-t border-white/5 px-2.5 py-1 text-[11px] text-muted-foreground">{status}</div>
        )}
      </div>
    </div>
  );
}

// ── Folder picker (a modal that browses and approves) ────────────────────────

function FolderPicker({ onClose, onPicked }: { onClose: () => void; onPicked: () => void }) {
  const t = useT();
  const [path, setPath] = useState<string | null>(null);
  const [entries, setEntries] = useState<BrowseEntry[]>([]);
  const [parent, setParent] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (target?: string) => {
    setBusy(true);
    try {
      const result = await browseFolders(target);
      setPath(result.path);
      setEntries(result.entries);
      setParent(result.parent);
      setError(result.reason);
    } catch {
      setError(t('editor.listFailed'));
    } finally {
      setBusy(false);
    }
  }, [t]);

  useEffect(() => { void load(undefined); }, [load]);

  const open = useCallback(async () => {
    if (!path) return;
    setBusy(true);
    try {
      const root = await approveTrustedRoot(path);
      await selectTrustedRoot(root.id);
      onPicked();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('editor.listFailed'));
      setBusy(false);
    }
  }, [path, onPicked, t]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div
        className="glass-card-strong flex max-h-[70vh] w-full max-w-lg flex-col overflow-hidden rounded-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="border-b border-white/5 px-3 py-2 text-[13px] font-medium text-foreground">
          {t('editor.chooseFolder')}
        </div>
        <div className="flex items-center gap-2 border-b border-white/5 px-3 py-1.5">
          <button
            type="button"
            disabled={!parent}
            onClick={() => parent && void load(parent)}
            className="rounded px-1.5 py-0.5 text-[11px] text-muted-foreground hover:text-foreground disabled:opacity-30"
          >
            ↑ {t('editor.up')}
          </button>
          <span className="truncate text-[11px] text-muted-foreground" title={path ?? ''}>
            {path ?? '—'}
          </span>
        </div>
        <div className="min-h-0 flex-1 overflow-auto p-1.5">
          {busy && entries.length === 0 && (
            <p className="p-2 text-[12px] text-muted-foreground">{t('editor.loading')}</p>
          )}
          {entries.filter((e) => e.isDir).map((entry) => (
            <button
              key={entry.path}
              type="button"
              onClick={() => void load(entry.path)}
              className="flex w-full items-center gap-1.5 rounded px-2 py-1 text-left text-[12px] text-foreground/80 hover:bg-white/5"
            >
              <span className="text-[10px] text-muted-foreground">▸</span>
              <span className="truncate">{entry.name}</span>
            </button>
          ))}
          {error && <p className="p-2 text-[11px] text-amber-300/80">{error}</p>}
        </div>
        <div className="flex items-center justify-end gap-2 border-t border-white/5 px-3 py-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-3 py-1.5 text-[12px] text-muted-foreground hover:text-foreground"
          >
            {t('editor.cancel')}
          </button>
          <button
            type="button"
            disabled={!path || busy}
            onClick={() => void open()}
            className="glass-button rounded-lg px-3 py-1.5 text-[12px] text-foreground disabled:opacity-40"
          >
            {t('editor.approve')}
          </button>
        </div>
      </div>
    </div>
  );
}

export default EditorScreen;

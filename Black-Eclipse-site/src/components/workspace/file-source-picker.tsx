'use client';

// ── File source picker (shared) ───────────────────────────────────────────────
// One surface that answers "where is this file from?" BEFORE a file is attached:
//
//   Project        — browse the chat's approved workspace folder (or the repo
//                    default). Every row shows its folder path; the picked file
//                    keeps that path as provenance.
//   This computer  — the OS file picker. The browser never reveals the absolute
//                    path, so these are honestly labelled "Local · uploaded
//                    copy" instead of pretending to know a folder.
//   Images         — the same local picker, filtered to images.
//
// It is portaled above the app and reuses the same confinement as the editor
// (`/api/workspace/files`), so browsing can never escape an approved root.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  Check,
  ChevronRight,
  FileText as FileIcon,
  Folder,
  FolderOpen,
  Server as HardDrive,
  Loader2,
  Redo2 as RotateCw,
  X,
} from '@/lib/icons';
import { cn } from '@/lib/utils';
import {
  listWorkspaceFiles,
  readWorkspaceFile,
  type EditorEntry,
  type TrustedRoot,
  type WorkspaceFileHit,
} from '@/lib/harness/clients/code-browser';
import { FolderPicker } from '@/components/workspace/folder-picker';
import {
  breadcrumbs,
  folderOf,
  formatBytes,
  joinRelative,
  parentDir,
  type PickedFile,
} from '@/lib/chat/file-sources';

interface ProjectBinding {
  workspaceRootId: string | null;
  workspacePath: string | null;
}

export interface FileSourcePickerProps {
  onClose: () => void;
  /** Called with the chosen files (already carrying their provenance). */
  onPick: (files: PickedFile[]) => void;
  /** The conversation whose bound project is the default browsing root. */
  chatId?: string | null;
  /** `images` restricts the picker to local image files. */
  mode?: 'all' | 'images';
  title?: string;
}

type Tab = 'project' | 'local';

function rootLabelFromPath(path: string | null | undefined): string {
  if (!path) return 'Eclipse repo';
  const parts = path.replace(/\\/g, '/').split('/').filter(Boolean);
  return parts[parts.length - 1] ?? path;
}

export function FileSourcePicker({
  onClose,
  onPick,
  chatId,
  mode = 'all',
  title,
}: FileSourcePickerProps) {
  const [mounted, setMounted] = useState(false);
  const [tab, setTab] = useState<Tab>(mode === 'images' ? 'local' : 'project');
  const [binding, setBinding] = useState<ProjectBinding | null>(null);
  const [roots, setRoots] = useState<TrustedRoot[]>([]);
  const [rootId, setRootId] = useState<string | null>(null);
  const [runtime, setRuntime] = useState<'ready' | 'unavailable' | 'error'>('ready');
  const [dir, setDir] = useState('.');
  const [entries, setEntries] = useState<EditorEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pickingFolder, setPickingFolder] = useState(false);
  const [selectedProject, setSelectedProject] = useState<Map<string, WorkspaceFileHit>>(new Map());
  const [localPicks, setLocalPicks] = useState<PickedFile[]>([]);
  const [attaching, setAttaching] = useState(false);
  const [attachError, setAttachError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => { setMounted(true); }, []);

  // Resolve the chat's project binding (root id + label) once.
  useEffect(() => {
    let alive = true;
    if (!chatId) { setRuntime('ready'); return; }
    void (async () => {
      try {
        const res = await fetch(`/api/chat/session/project?chatId=${encodeURIComponent(chatId)}`, {
          cache: 'no-store',
        });
        const data = (await res.json().catch(() => ({}))) as {
          project?: ProjectBinding | null;
          roots?: TrustedRoot[];
          runtime?: 'ready' | 'unavailable' | 'error';
        };
        if (!alive) return;
        setBinding(data.project ?? null);
        setRoots(Array.isArray(data.roots) ? data.roots : []);
        setRootId(data.project?.workspaceRootId ?? null);
        setRuntime(data.runtime ?? 'ready');
      } catch {
        if (alive) setRuntime('error');
      }
    })();
    return () => { alive = false; };
  }, [chatId]);

  const activeRoot = roots.find((root) => root.id === rootId) ?? null;
  const projectLabel = activeRoot?.label?.trim()
    || rootLabelFromPath(binding?.workspacePath ?? activeRoot?.path);

  const load = useCallback(async (nextDir: string) => {
    setLoading(true);
    setError(null);
    try {
      const result = await listWorkspaceFiles(nextDir, rootId);
      setDir(result.path || nextDir);
      setEntries(result.entries);
    } catch (err) {
      setEntries([]);
      setError(err instanceof Error ? err.message : 'That folder could not be listed.');
    } finally {
      setLoading(false);
    }
  }, [rootId]);

  // First load + reload when the root selection changes.
  useEffect(() => { void load('.'); }, [load]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); onClose(); }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  const files = useMemo(() => entries.filter((entry) => !entry.isDir), [entries]);
  const folders = useMemo(() => entries.filter((entry) => entry.isDir), [entries]);

  const toggleProject = (entry: EditorEntry) => {
    setSelectedProject((prev) => {
      const next = new Map(prev);
      if (next.has(entry.path)) next.delete(entry.path);
      else next.set(entry.path, { name: entry.name, path: entry.path, bytes: null });
      return next;
    });
  };

  const addLocal = (list: FileList | null) => {
    if (!list) return;
    const picked: PickedFile[] = Array.from(list).map((file) => ({
      file,
      meta: { origin: 'upload' },
    }));
    setLocalPicks((prev) => [...prev, ...picked]);
  };

  const removeLocal = (name: string) => {
    setLocalPicks((prev) => prev.filter((picked) => picked.file.name !== name));
  };

  const attach = useCallback(async () => {
    setAttaching(true);
    setAttachError(null);
    try {
      if (tab === 'local') {
        if (localPicks.length === 0) return;
        onPick(localPicks);
        onClose();
        return;
      }
      // Project files are read through the confined editor route and attached as
      // text. A binary/unreadable file is reported, never silently attached.
      const chosen = [...selectedProject.values()];
      if (chosen.length === 0) return;
      const picked: PickedFile[] = [];
      const failed: string[] = [];
      for (const hit of chosen) {
        try {
          const result = await readWorkspaceFile(hit.path, rootId);
          picked.push({
            file: new File([result.content], hit.name, { type: 'text/plain' }),
            meta: {
              origin: 'project',
              sourcePath: result.path || hit.path,
              rootId,
              rootLabel: projectLabel,
            },
          });
        } catch {
          failed.push(hit.name);
        }
      }
      if (picked.length > 0) onPick(picked);
      if (failed.length > 0) {
        setAttachError(
          failed.length === 1
            ? `${failed[0]} isn't readable text, so it can't be used as context.`
            : `${failed.length} files aren't readable text and were skipped.`,
        );
        if (picked.length === 0) return;
      }
      onClose();
    } catch (err) {
      setAttachError(err instanceof Error ? err.message : 'Could not attach those files.');
    } finally {
      setAttaching(false);
    }
  }, [tab, localPicks, selectedProject, rootId, projectLabel, onPick, onClose]);

  const selectRoot = (id: string | null) => {
    setRootId(id);
    setSelectedProject(new Map());
    setDir('.');
  };

  const breadcrumb = breadcrumbs(dir);
  const locationLabel = dir === '.' ? (rootId ? projectLabel : 'Eclipse repo') : joinRelative(projectLabel, dir);

  const dialog = (
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center bg-black/60 p-3 backdrop-blur-sm sm:p-6"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title ?? 'Add files'}
        className="glass-card-strong flex max-h-[84vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-border/40 shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start gap-3 border-b border-border/30 px-4 py-3">
          <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-primary/15 text-primary">
            <FolderOpen size={18} />
          </span>
          <div className="min-w-0 flex-1">
            <h2 className="text-[15px] font-semibold text-foreground">
              {title ?? (mode === 'images' ? 'Add images' : 'Add files')}
            </h2>
            <p className="mt-0.5 text-[11.5px] text-muted-foreground">
              Pick project files in place, or upload from this computer.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="shrink-0 rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <X size={16} />
          </button>
        </div>

        {/* Source tabs */}
        {mode === 'all' && (
          <div className="flex items-center gap-1 border-b border-border/30 px-3 py-1.5" role="tablist">
            <TabButton active={tab === 'project'} onClick={() => setTab('project')} icon={<Folder size={13} />}>
              Project
            </TabButton>
            <TabButton active={tab === 'local'} onClick={() => setTab('local')} icon={<HardDrive size={13} />}>
              This computer
            </TabButton>
            <span className="ml-auto truncate text-[10.5px] text-muted-foreground/60" title={locationLabel}>
              {tab === 'project' ? locationLabel : 'Local uploads are copied into this chat'}
            </span>
          </div>
        )}

        {tab === 'project' ? (
          <>
            {/* Root + breadcrumb */}
            <div className="flex flex-wrap items-center gap-1.5 border-b border-border/30 px-3 py-2">
              {roots.length > 1 && (
                <select
                  value={rootId ?? ''}
                  onChange={(event) => selectRoot(event.target.value || null)}
                  aria-label="Project folder"
                  className="h-8 max-w-[180px] rounded-lg border border-border/40 bg-black/20 px-2 text-[11.5px] text-foreground outline-none focus:border-primary"
                >
                  <option value="">Eclipse repo (default)</option>
                  {roots.map((root) => (
                    <option key={root.id} value={root.id}>
                      {root.label?.trim() || rootLabelFromPath(root.path)}
                    </option>
                  ))}
                </select>
              )}
              <button
                type="button"
                disabled={dir === '.'}
                onClick={() => void load(parentDir(dir))}
                className="inline-flex h-8 items-center rounded-lg px-2 text-[11.5px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:opacity-30"
              >
                ↑ Up
              </button>
              <div className="flex min-w-0 flex-1 flex-wrap items-center gap-0.5 text-[11.5px]">
                <button
                  type="button"
                  onClick={() => void load('.')}
                  className="rounded px-1 py-0.5 font-medium text-foreground/90 hover:bg-accent"
                >
                  {projectLabel}
                </button>
                {breadcrumb.map((part, index) => {
                  const target = breadcrumb.slice(0, index + 1).join('/');
                  return (
                    <span key={target} className="flex min-w-0 items-center gap-0.5">
                      <ChevronRight size={11} className="shrink-0 text-muted-foreground/40" />
                      <button
                        type="button"
                        onClick={() => void load(target)}
                        className="max-w-[140px] truncate rounded px-1 py-0.5 text-muted-foreground hover:bg-accent hover:text-foreground"
                      >
                        {part}
                      </button>
                    </span>
                  );
                })}
              </div>
              <button
                type="button"
                disabled={loading}
                onClick={() => void load(dir)}
                title="Reload this folder"
                className="inline-flex h-8 items-center rounded-lg px-2 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:opacity-40"
              >
                <RotateCw size={13} className={cn(loading && 'animate-spin')} />
              </button>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
              {runtime !== 'ready' && (
                <p className="mx-2 my-2 rounded-lg border border-amber-500/25 bg-amber-500/5 px-2.5 py-1.5 text-[11px] text-amber-300/90">
                  {runtime === 'unavailable'
                    ? 'The Eclipse runtime is not running, so project folders cannot be listed. You can still upload from this computer.'
                    : 'Could not read the project folders just now.'}
                </p>
              )}
              {loading && entries.length === 0 && (
                <div className="flex items-center justify-center gap-2 py-10 text-[12px] text-muted-foreground">
                  <Loader2 size={15} className="animate-spin" /> Reading folder…
                </div>
              )}
              {error && !loading && (
                <div className="mx-2 my-2 rounded-xl border border-amber-500/25 bg-amber-500/5 p-2.5 text-[11.5px] text-amber-300/90">
                  {error}
                </div>
              )}
              {!loading && !error && entries.length === 0 && (
                <p className="px-3 py-8 text-center text-[12px] text-muted-foreground/70">
                  This folder is empty.
                </p>
              )}
              <div className="space-y-0.5">
                {folders.map((entry) => (
                  <button
                    key={entry.path}
                    type="button"
                    onClick={() => void load(entry.path)}
                    className="group flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left transition-colors hover:bg-accent"
                  >
                    <Folder size={14} className="shrink-0 text-muted-foreground/70" />
                    <span className="min-w-0 flex-1 truncate text-[12.5px] text-foreground/90">{entry.name}</span>
                    <ChevronRight size={13} className="shrink-0 text-muted-foreground/40" />
                  </button>
                ))}
                {files.map((entry) => {
                  const checked = selectedProject.has(entry.path);
                  return (
                    <button
                      key={entry.path}
                      type="button"
                      onClick={() => toggleProject(entry)}
                      className={cn(
                        'flex w-full items-start gap-2 rounded-lg px-2.5 py-1.5 text-left transition-colors hover:bg-accent',
                        checked && 'bg-primary/10',
                      )}
                    >
                      <span
                        className={cn(
                          'mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border',
                          checked ? 'border-primary bg-primary text-primary-foreground' : 'border-border/50',
                        )}
                      >
                        {checked ? <Check size={11} /> : null}
                      </span>
                      <FileIcon size={14} className="mt-0.5 shrink-0 text-muted-foreground/70" />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[12.5px] text-foreground/90">{entry.name}</span>
                        <span className="block truncate font-mono text-[10px] text-muted-foreground/60" title={entry.path}>
                          {folderOf(entry.path) || projectLabel}
                        </span>
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          </>
        ) : (
          <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              className="flex w-full flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border/50 bg-black/10 px-4 py-8 text-center transition-colors hover:border-primary/50 hover:bg-primary/5"
            >
              <HardDrive size={22} className="text-primary/80" />
              <span className="text-[13px] font-medium text-foreground">
                Choose {mode === 'images' ? 'images' : 'files'} from this computer
              </span>
              <span className="max-w-sm text-[11px] text-muted-foreground/70">
                The browser does not reveal the folder, so these show as a local uploaded copy.
              </span>
            </button>
            <input
              ref={inputRef}
              type="file"
              multiple
              accept={mode === 'images' ? 'image/*' : undefined}
              className="hidden"
              onChange={(event) => { addLocal(event.target.files); event.target.value = ''; }}
            />
            {localPicks.length > 0 && (
              <ul className="mt-3 space-y-1">
                {localPicks.map((picked) => (
                  <li
                    key={picked.file.name}
                    className="flex items-center gap-2 rounded-lg border border-border/30 bg-white/[0.03] px-2.5 py-1.5"
                  >
                    <FileIcon size={13} className="shrink-0 text-muted-foreground/70" />
                    <span className="min-w-0 flex-1 truncate text-[12px] text-foreground/90">{picked.file.name}</span>
                    <span className="shrink-0 rounded-full bg-accent/40 px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-muted-foreground/70">
                      Local
                    </span>
                    <span className="shrink-0 text-[10px] text-muted-foreground/60">{formatBytes(picked.file.size)}</span>
                    <button
                      type="button"
                      onClick={() => removeLocal(picked.file.name)}
                      aria-label={`Remove ${picked.file.name}`}
                      className="shrink-0 rounded p-0.5 text-muted-foreground/60 hover:text-foreground"
                    >
                      <X size={12} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {/* Footer */}
        <div className="flex flex-wrap items-center gap-2 border-t border-border/30 px-4 py-2.5">
          <span className="min-w-0 flex-1 truncate text-[10.5px] text-muted-foreground/70">
            {attachError ? <span className="text-amber-300/90">{attachError}</span> : locationLabel}
          </span>
          <button
            type="button"
            onClick={() => setPickingFolder(true)}
            className="inline-flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-[11.5px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <FolderOpen size={13} /> Open folder…
          </button>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-8 items-center rounded-lg px-3 text-[12px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={attaching || (tab === 'project' ? selectedProject.size === 0 : localPicks.length === 0)}
            onClick={() => void attach()}
            className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-primary px-3.5 text-[12px] font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-40"
          >
            {attaching && <Loader2 size={12} className="animate-spin" />}
            {attaching
              ? 'Adding…'
              : tab === 'project'
                ? `Add ${selectedProject.size || ''} file${selectedProject.size === 1 ? '' : 's'}`.replace('  ', ' ')
                : `Add ${localPicks.length || ''} file${localPicks.length === 1 ? '' : 's'}`.replace('  ', ' ')}
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <>
      {mounted ? createPortal(dialog, document.body) : null}
      {pickingFolder ? (
        <FolderPicker
          onClose={() => setPickingFolder(false)}
          onApproved={(root) => {
            setPickingFolder(false);
            setRoots((prev) => (prev.some((r) => r.id === root.id) ? prev : [...prev, root]));
            selectRoot(root.id);
          }}
          approveLabel="Use this folder"
        />
      ) : null}
    </>
  );
}

function TabButton({
  active,
  onClick,
  icon,
  children,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-[11.5px] font-medium transition-colors',
        active ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:bg-accent hover:text-foreground',
      )}
    >
      {icon}
      {children}
    </button>
  );
}

export default FileSourcePicker;

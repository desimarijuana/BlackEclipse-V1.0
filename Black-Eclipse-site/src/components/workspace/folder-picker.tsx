'use client';

// ── Folder picker (shared) ─────────────────────────────────────────────────────
// A modal that browses the filesystem (read-only, bounded) and approves one
// folder as a workspace root. Reused by the Editor screen and the chat project
// chip. It never writes files; approval is the one operator act.

import { useCallback, useEffect, useState } from 'react';
import { useT } from '@/lib/i18n/use-t';
import {
  approveTrustedRoot,
  browseFolders,
  selectTrustedRoot,
  type BrowseEntry,
  type TrustedRoot,
} from '@/lib/harness/code-browser';

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

export function FolderPicker({
  onClose,
  onApproved,
  selectGlobally = false,
  approveLabel,
}: FolderPickerProps) {
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
      if (selectGlobally) await selectTrustedRoot(root.id);
      onApproved(root);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('editor.listFailed'));
      setBusy(false);
    }
  }, [path, onApproved, selectGlobally, t]);

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div
        className="glass-card-strong flex max-h-[70vh] w-full max-w-lg flex-col overflow-hidden rounded-2xl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={t('editor.chooseFolder')}
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
            {approveLabel ?? t('editor.approve')}
          </button>
        </div>
      </div>
    </div>
  );
}

export default FolderPicker;

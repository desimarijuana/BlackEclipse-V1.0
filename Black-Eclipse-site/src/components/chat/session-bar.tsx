'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Folder,
  FolderOpen,
  FileText,
  FileOutput,
  Paperclip,
  Download,
  Trash2,
  Loader2,
  ChevronUp,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  deleteSessionFile,
  fetchSession,
  sessionFileUrl,
  uploadSessionFile,
} from '@/lib/chat/session-client';
import {
  SESSION_LIMITS,
  type SessionFile,
  type SessionInfo,
} from '@/lib/chat/session-types';

interface SessionBarProps {
  chatId: string | null;
  /** Bumped by the parent after a run so new output files appear immediately. */
  refreshKey?: number;
  compact?: boolean;
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

/**
 * The conversation's workspace folder: where attached context lives and where
 * the agent's answers are stored. Collapsed by default so it never competes
 * with the chat; expands into a small file list with add/download/remove.
 */
export function SessionBar({ chatId, refreshKey = 0, compact = false }: SessionBarProps) {
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const reload = useCallback(async () => {
    if (!chatId) {
      setSession(null);
      return;
    }
    try {
      setSession(await fetchSession(chatId));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load session folder");
    }
  }, [chatId]);

  useEffect(() => { void reload(); }, [reload, refreshKey]);

  const handleFiles = async (files: FileList | null) => {
    if (!files || !files.length || !chatId) return;
    setBusy(true);
    setError(null);
    try {
      for (const file of Array.from(files)) {
        if (file.size > SESSION_LIMITS.maxFileBytes) {
          throw new Error(`${file.name} exceeds ${Math.round(SESSION_LIMITS.maxFileBytes / 1024 / 1024)}MB`);
        }
        const bytes = new Uint8Array(await file.arrayBuffer());
        await uploadSessionFile(chatId, "context", file.name, bytes);
      }
      setOpen(true);
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  const remove = async (file: SessionFile) => {
    if (!chatId) return;
    setBusy(true);
    try {
      await deleteSessionFile(chatId, file.kind, file.name);
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setBusy(false);
    }
  };

  const contextFiles = session?.files.filter((f) => f.kind === "context") ?? [];
  const outputFiles = session?.files.filter((f) => f.kind === "output") ?? [];

  if (!chatId) return null;

  return (
    <div className={cn("w-full", compact ? "text-[11px]" : "text-xs")}>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className={cn(
            'flex items-center gap-1.5 rounded-full px-2.5 py-1 transition-colors cursor-pointer',
            'text-muted-foreground hover:bg-accent hover:text-foreground',
          )}
          title={session?.path}
        >
          {open ? <FolderOpen size={13} /> : <Folder size={13} />}
          <span className="font-medium">Session</span>
          <span className="text-muted-foreground/60">
            {contextFiles.length + outputFiles.length}
          </span>
          <ChevronUp size={12} className={cn('transition-transform', open ? '' : 'rotate-180')} />
        </button>

        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={busy}
          className="flex items-center gap-1.5 rounded-full px-2.5 py-1 text-muted-foreground hover:bg-accent hover:text-foreground transition-colors cursor-pointer disabled:opacity-50"
          title="Add documents as context"
        >
          {busy ? <Loader2 size={13} className="animate-spin" /> : <Paperclip size={13} />}
          <span className="hidden sm:inline">Add docs</span>
        </button>

        <input
          ref={inputRef}
          type="file"
          multiple
          className="hidden"
          onChange={(e) => void handleFiles(e.target.files)}
        />

        {session && (
          <span
            className="hidden min-[900px]:block truncate font-mono text-[10px] text-muted-foreground/50"
            title={session.path}
          >
            {session.path}
          </span>
        )}
      </div>

      {error && <p className="mt-1 text-[11px] text-amber-400/80">{error}</p>}

      {open && session && (
        <div className="mt-1.5 glass-card rounded-xl border border-white/10 dark:border-white/5 p-2 space-y-2">
          {contextFiles.length === 0 && outputFiles.length === 0 && (
            <p className="px-1 py-0.5 text-[11px] text-muted-foreground">
              No files yet. Add documents to give the agent context; answers are saved here automatically.
            </p>
          )}

          {contextFiles.length > 0 && (
            <FileGroup label="Context" icon={FileText} files={contextFiles} chatId={chatId} onRemove={remove} />
          )}
          {outputFiles.length > 0 && (
            <FileGroup label="Output" icon={FileOutput} files={outputFiles} chatId={chatId} onRemove={remove} />
          )}
        </div>
      )}
    </div>
  );
}

function FileGroup({
  label,
  icon: Icon,
  files,
  chatId,
  onRemove,
}: {
  label: string;
  icon: typeof FileText;
  files: SessionFile[];
  chatId: string;
  onRemove: (file: SessionFile) => void;
}) {
  return (
    <div>
      <p className="px-1 pb-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground/60">
        {label}
      </p>
      <ul className="space-y-0.5">
        {files.map((file) => (
          <li key={`${file.kind}:${file.name}`} className="group flex items-center gap-2 rounded-lg px-1.5 py-1 hover:bg-accent/40">
            <Icon size={12} className="shrink-0 text-muted-foreground" />
            <span className="min-w-0 flex-1 truncate text-foreground/85" title={file.name}>
              {file.name}
            </span>
            <span className="shrink-0 text-[10px] text-muted-foreground/70">{formatBytes(file.bytes)}</span>
            <a
              href={sessionFileUrl(chatId, file.kind, file.name)}
              download={file.name}
              className="shrink-0 rounded p-0.5 text-muted-foreground hover:text-foreground"
              title="Download"
            >
              <Download size={12} />
            </a>
            <button
              type="button"
              onClick={() => onRemove(file)}
              className="shrink-0 rounded p-0.5 text-muted-foreground hover:text-red-400"
              title="Remove"
            >
              <Trash2 size={12} />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

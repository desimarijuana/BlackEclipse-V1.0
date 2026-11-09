'use client';

import { useState } from 'react';
import {
  Folder,
  FolderOpen,
  FileText,
  FileOutput,
  Download,
  Trash2,
  Loader2,
  ChevronUp,
} from '@/lib/icons';
import { cn } from '@/lib/utils';
import { sessionFileUrl } from '@/lib/chat/session-client';
import type { SessionController } from '@/lib/chat/use-session';
import type { SessionFile } from '@/lib/chat/session-types';

interface SessionBarProps {
  session: SessionController;
  compact?: boolean;
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

/**
 * The conversation's workspace folder: where attached context lives and where
 * the agent's answers are stored. Display-only — adding documents is the
 * composer's "+" button (which uploads into this same session), so there is one
 * attach affordance instead of two. Collapsed by default.
 */
export function SessionBar({ session: controller, compact = false }: SessionBarProps) {
  const { session, busy, error, pending, removeFile, removePending } = controller;
  const [open, setOpen] = useState(false);

  const chatId = session?.chatId;
  const contextFiles = session?.files.filter((f) => f.kind === 'context') ?? [];
  const outputFiles = session?.files.filter((f) => f.kind === 'output') ?? [];
  const total = contextFiles.length + outputFiles.length + pending.length;

  if (total === 0 && !error) return null;

  return (
    <div className={cn('w-full', compact ? 'text-[11px]' : 'text-xs')}>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex items-center gap-1.5 rounded-full px-2.5 py-1 text-muted-foreground hover:bg-accent hover:text-foreground transition-colors cursor-pointer"
          title={session?.path}
        >
          {open ? <FolderOpen size={13} /> : <Folder size={13} />}
          <span className="font-medium">{chatId ? 'Session' : 'Attached'}</span>
          <span className="text-muted-foreground/60">{total}</span>
          <ChevronUp size={12} className={cn('transition-transform', open ? '' : 'rotate-180')} />
        </button>

        {busy && <Loader2 size={12} className="animate-spin text-muted-foreground" />}

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

      {open && (
        <div className="mt-1.5 glass-card rounded-xl border border-white/10 dark:border-white/5 p-2 space-y-2">
          {pending.length > 0 && (
            <FileGroup
              label={chatId ? 'Attaching' : 'Attached — sent with your first message'}
              icon={FileText}
              files={pending.map((p) => ({ origin: 'upload' as const, name: p.name, kind: 'context' as const, bytes: p.bytes, updatedAt: '', textExtractable: true }))}
              chatId={chatId ?? ''}
              onRemove={(f) => removePending(f.name)}
              downloadable={false}
            />
          )}
          {contextFiles.length > 0 && (
            <FileGroup label="Context" icon={FileText} files={contextFiles} chatId={chatId ?? ''} onRemove={removeFile} />
          )}
          {outputFiles.length > 0 && (
            <FileGroup label="Output" icon={FileOutput} files={outputFiles} chatId={chatId ?? ''} onRemove={removeFile} />
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
  downloadable = true,
}: {
  label: string;
  icon: typeof FileText;
  files: SessionFile[];
  chatId: string;
  onRemove: (file: SessionFile) => void;
  downloadable?: boolean;
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
            {downloadable && chatId && (
              <a
                href={sessionFileUrl(chatId, file.kind, file.name)}
                download={file.name}
                className="shrink-0 rounded p-0.5 text-muted-foreground hover:text-foreground"
                title="Download"
              >
                <Download size={12} />
              </a>
            )}
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

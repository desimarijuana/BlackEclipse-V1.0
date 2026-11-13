'use client';

// ── Mention palette ─────────────────────────────────────────────────────────
// The `@` listbox for both bots/rooms and project files. Extracted from the
// composer so the composer stays under the file-size ceiling; it is a portal
// anchored to the composer's measured box.

import { createPortal } from 'react-dom';
import { Bot, FileText, Loader2, Users } from '@/lib/icons';
import { BotAvatar } from '@/components/bots/bot-avatar';
import { GhostAvatar } from '@/components/bots/ghost-avatar';
import { avatarFor } from '@/lib/bots/avatar-store';
import { ghostSpecFromId, type GhostSpec } from '@/lib/bots/ghost';
import { folderOf, type FileRef } from '@/lib/chat/file-sources';
import type { MentionTarget } from '@/lib/bots/mentions';
import { cn } from '@/lib/utils';

export type MentionOption =
  | { kind: 'bot'; target: MentionTarget }
  | { kind: 'file'; file: FileRef };

export interface MentionPaletteProps {
  open: boolean;
  box: { left: number; width: number; bottom: number } | null;
  label: string;
  options: MentionOption[];
  highlight: number;
  onHighlight: (index: number) => void;
  onSelect: (option: MentionOption) => void;
  searching: boolean;
  listRef: React.RefObject<HTMLDivElement | null>;
  avatars: Record<string, GhostSpec>;
}

export function MentionPalette({
  open,
  box,
  label,
  options,
  highlight,
  onHighlight,
  onSelect,
  searching,
  listRef,
  avatars,
}: MentionPaletteProps) {
  if (!open || !box || typeof document === 'undefined') return null;

  return createPortal(
    <div
      ref={listRef}
      role="listbox"
      aria-label={label}
      style={{ position: 'fixed', left: box.left, width: box.width, bottom: box.bottom }}
      className="z-[120] max-h-[50vh] overflow-y-auto rounded-2xl glass-command-popover shadow-lg"
    >
      <div className="flex items-center justify-between px-3 pt-2 pb-1">
        <span className="text-[10px] uppercase tracking-wide text-muted-foreground/60">{label}</span>
        {searching && <Loader2 size={11} className="animate-spin text-muted-foreground/50" />}
      </div>
      {options.map((option, i) => {
        const active = i === highlight;
        if (option.kind === 'file') {
          const file = option.file;
          return (
            <button
              key={`file:${file.path}`}
              type="button"
              role="option"
              aria-selected={active}
              onMouseEnter={() => onHighlight(i)}
              onMouseDown={(e) => {
                e.preventDefault();
                onSelect(option);
              }}
              className={cn(
                'flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors',
                active ? 'bg-accent/40' : 'hover:bg-accent/25',
              )}
            >
              <FileText size={15} className="shrink-0 text-primary/80" />
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium text-foreground/90">{file.name}</span>
                <span className="block truncate font-mono text-[10px] text-muted-foreground/60">
                  {folderOf(file.path) || file.rootLabel || '.'}
                </span>
              </span>
              <span className="ml-auto inline-flex shrink-0 items-center gap-1 rounded-full bg-accent/30 px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-muted-foreground/70">
                {file.rootLabel?.trim() || 'Project'}
              </span>
            </button>
          );
        }
        const m = option.target;
        return (
          <button
            key={`${m.kind}:${m.id}`}
            type="button"
            role="option"
            aria-selected={active}
            onMouseEnter={() => onHighlight(i)}
            // onMouseDown (not onClick) so the textarea does not blur/lose the
            // selection before the mention is inserted.
            onMouseDown={(e) => {
              e.preventDefault();
              onSelect(option);
            }}
            className={cn(
              'flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors',
              active ? 'bg-accent/40' : 'hover:bg-accent/25',
            )}
          >
            {m.kind === 'group' ? (
              <GhostAvatar spec={ghostSpecFromId(m.id)} size={18} title={m.name} />
            ) : (
              <BotAvatar botId={m.id} spec={avatarFor(avatars, m.id)} size={18} title={m.name} />
            )}
            <span className="min-w-0 shrink-0 truncate font-medium">@{m.name}</span>
            {m.description && (
              <span className="hidden min-w-0 flex-1 truncate text-[11px] text-muted-foreground/70 sm:inline">
                {m.description}
              </span>
            )}
            <span className="ml-auto inline-flex shrink-0 items-center gap-1 rounded-full bg-accent/30 px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-muted-foreground/70">
              {m.kind === 'group' ? <Users size={9} /> : <Bot size={9} />}
              {m.kind}
            </span>
          </button>
        );
      })}
    </div>,
    document.body,
  );
}

export default MentionPalette;

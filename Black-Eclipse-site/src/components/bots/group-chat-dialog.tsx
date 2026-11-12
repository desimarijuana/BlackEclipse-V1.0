'use client';

// ── New group chat dialog ─────────────────────────────────────────────────────
// Gather 2–6 of the user's bots into one room. Members keep their own identity;
// the room (name, members, optional photo) is persisted client-side through the
// groups store. Replies in the room still come from the real harness.

import { useEffect, useMemo, useRef, useState } from 'react';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n';
import { Check, ImagePlus, Search, Users } from '@/lib/icons';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { BotAvatar } from '@/components/bots/bot-avatar';
import { avatarFor, useBotAvatarStore, useHydrateBotAvatars } from '@/lib/bots/avatar-store';
import { fileToAvatarDataUrl } from '@/lib/bots/image';
import type { AutomationView } from '@/lib/harness/clients/automation-browser';

const MIN_MEMBERS = 2;
const MAX_MEMBERS = 6;

export interface GroupChatDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  bots: AutomationView[];
  onCreate: (input: { name: string; memberIds: string[]; image?: string }) => void;
}

/** A short, stable @handle for a bot, derived from its name (never fetched). */
export function botHandle(name: string): string {
  const slug = name.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
  return `@${slug || 'bot'}`;
}

export function GroupChatDialog({ open, onOpenChange, bots, onCreate }: GroupChatDialogProps) {
  const t = useT();
  useHydrateBotAvatars();
  const avatars = useBotAvatarStore((s) => s.avatars);
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState<string[]>([]);
  const [name, setName] = useState('');
  const [image, setImage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setQuery('');
    setSelected([]);
    setName('');
    setImage(null);
    setError(null);
  }, [open]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return bots;
    return bots.filter((b) =>
      b.name.toLowerCase().includes(q) || (b.description ?? '').toLowerCase().includes(q),
    );
  }, [bots, query]);

  const toggle = (id: string) => {
    setError(null);
    setSelected((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id);
      if (prev.length >= MAX_MEMBERS) return prev;
      return [...prev, id];
    });
  };

  const onUpload = async (file: File | undefined) => {
    if (!file) return;
    try {
      setImage(await fileToAvatarDataUrl(file));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not read the image.');
    }
  };

  const create = () => {
    if (!name.trim()) { setError(t('bots.groups.nameRequired')); return; }
    if (selected.length < MIN_MEMBERS) { setError(t('bots.groups.minMembers')); return; }
    onCreate({ name: name.trim(), memberIds: selected, image: image ?? undefined });
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="glass-card-strong max-h-[92vh] overflow-y-auto rounded-2xl border border-white/15 dark:border-white/10 sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t('bots.groups.dialogTitle')}</DialogTitle>
          <DialogDescription>{t('bots.groups.dialogHint')}</DialogDescription>
        </DialogHeader>

        <div className="relative">
          <Search size={14} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('bots.groups.search')}
            className="pl-8"
            aria-label={t('bots.groups.search')}
          />
        </div>

        <ul className="max-h-56 space-y-1 overflow-y-auto pr-0.5">
          {filtered.length === 0 ? (
            <li className="px-2 py-3 text-xs text-muted-foreground">{t('bots.noMatches')}</li>
          ) : (
            filtered.map((bot) => {
              const isSelected = selected.includes(bot.id);
              const disabled = !isSelected && selected.length >= MAX_MEMBERS;
              return (
                <li key={bot.id}>
                  <button
                    type="button"
                    onClick={() => toggle(bot.id)}
                    disabled={disabled}
                    aria-pressed={isSelected}
                    className={cn(
                      'flex w-full items-center gap-2.5 rounded-xl px-2 py-1.5 text-left transition-colors',
                      isSelected ? 'bg-white/[0.08]' : 'hover:bg-white/[0.04]',
                      disabled && 'opacity-40',
                    )}
                  >
                    <BotAvatar botId={bot.id} spec={avatarFor(avatars, bot.id)} size={32} title={bot.name} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-xs font-semibold text-foreground">{bot.name}</span>
                      <span className="block truncate text-[10px] text-muted-foreground">{botHandle(bot.name)}</span>
                    </span>
                    <span
                      className={cn(
                        'flex h-4 w-4 shrink-0 items-center justify-center rounded border',
                        isSelected ? 'border-primary bg-primary text-primary-foreground' : 'border-border/60',
                      )}
                    >
                      {isSelected && <Check size={11} weight="bold" />}
                    </span>
                  </button>
                </li>
              );
            })
          )}
        </ul>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            className="glass-card-subtle inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground cursor-pointer"
          >
            {image ? (
              <img src={image} alt="" className="h-4 w-4 rounded object-cover" />
            ) : (
              <ImagePlus size={14} />
            )}
            {t('bots.groups.upload')}
          </button>
          <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
            <Users size={13} /> {t('bots.groups.selected', { count: selected.length })}
          </span>
        </div>

        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(e) => { void onUpload(e.target.files?.[0]); e.target.value = ''; }}
        />

        <Input
          value={name}
          onChange={(e) => { setName(e.target.value); setError(null); }}
          placeholder={t('bots.groups.namePlaceholder')}
          aria-label={t('bots.groups.namePlaceholder')}
        />

        {error && (
          <div className="rounded-lg border border-rose-500/30 bg-rose-500/5 px-3 py-2 text-xs text-rose-300">
            {error}
          </div>
        )}

        <DialogFooter className="gap-2">
          <Button variant="ghost" onClick={() => onOpenChange(false)}>{t('bots.groups.cancel')}</Button>
          <Button onClick={create} disabled={selected.length < MIN_MEMBERS || !name.trim()}>
            {t('bots.groups.create')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

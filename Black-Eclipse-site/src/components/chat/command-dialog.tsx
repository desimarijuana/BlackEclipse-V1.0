'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Command } from '@/lib/icons';
import { useT } from '@/lib/i18n/use-t';
import { useCommandMemory } from '@/lib/harness/command-history';
import { useProjectCommands } from '@/lib/harness/use-project-commands';
import type { CommandSpec } from '@/lib/harness/command-registry';
import { buildCommandPalette, CommandPaletteBody } from './command-palette';

export interface CommandPaletteDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSelect: (spec: CommandSpec) => void;
}

/**
 * The ⌘K / Ctrl+K command surface. It is independent of the composer draft: the
 * selection inserts `/name ` into the composer and closes. Recents and pins are
 * shared with the inline palette through the same client store.
 */
export function CommandPaletteDialog({ open, onOpenChange, onSelect }: CommandPaletteDialogProps) {
  const t = useT();
  const { history, favorites } = useCommandMemory();
  const projectCommands = useProjectCommands();
  const [search, setSearch] = useState('');
  const [highlight, setHighlight] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);

  const model = useMemo(
    () => buildCommandPalette(search, history.map((entry) => entry.name), favorites, projectCommands),
    [search, history, favorites, projectCommands],
  );

  useEffect(() => {
    if (!open) return;
    setSearch('');
    setHighlight(0);
  }, [open]);

  useEffect(() => {
    if (highlight >= model.flat.length) setHighlight(0);
  }, [highlight, model.flat.length]);

  useEffect(() => {
    if (!open) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previous;
    };
  }, [open]);

  useEffect(() => {
    const el = listRef.current?.querySelector<HTMLElement>('[aria-selected="true"]');
    el?.scrollIntoView({ block: 'nearest' });
  }, [highlight, model.flat.length, open]);

  if (!open || typeof document === 'undefined') return null;

  const choose = (spec: CommandSpec | undefined) => {
    if (!spec) return;
    onOpenChange(false);
    onSelect(spec);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.nativeEvent.isComposing) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setHighlight((h) => (h + 1) % Math.max(1, model.flat.length));
      return;
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlight((h) => (h - 1 + model.flat.length) % Math.max(1, model.flat.length));
      return;
    }
    if (e.key === 'Enter' || e.key === 'Tab') {
      e.preventDefault();
      choose(model.flat[Math.min(highlight, model.flat.length - 1)]);
      return;
    }
    if (e.key === 'Escape' || ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k')) {
      e.preventDefault();
      onOpenChange(false);
    }
  };

  return createPortal(
    <div
      className="fixed inset-0 z-[130] flex items-start justify-center bg-black/50 p-4 pt-[10vh] backdrop-blur-sm sm:pt-[14vh]"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onOpenChange(false);
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t('code.command.dialogLabel')}
        className="glass-card-strong flex max-h-[74vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-white/10 shadow-2xl shadow-black/40"
      >
        <div className="flex shrink-0 items-center gap-2 border-b border-white/5 px-3 py-2.5">
          <Command size={15} className="shrink-0 text-primary" />
          <input
            autoFocus
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setHighlight(0);
            }}
            onKeyDown={onKeyDown}
            placeholder={t('code.command.searchPlaceholder')}
            aria-label={t('code.command.searchPlaceholder')}
            className="min-w-0 flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
          />
          <kbd className="shrink-0 rounded border border-white/10 bg-accent/30 px-1.5 py-0.5 font-mono text-[9px] text-muted-foreground/60">
            esc
          </kbd>
        </div>
        <CommandPaletteBody
          sections={model.sections}
          flat={model.flat}
          highlight={highlight}
          query={search}
          favorites={favorites}
          layout="dialog"
          onHighlight={setHighlight}
          onSelect={choose}
          listRef={listRef}
        />
        <div className="shrink-0 border-t border-white/5 px-3 py-1.5 text-[10px] text-muted-foreground/50">
          {t('code.command.selectHint')}
        </div>
      </div>
    </div>,
    document.body,
  );
}

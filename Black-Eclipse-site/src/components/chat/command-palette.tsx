'use client';

import { useEffect, useMemo, useRef, useState, type RefObject } from 'react';
import { createPortal } from 'react-dom';
import { Command, Star } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n/use-t';
import {
  commandArgHint,
  isCommandAvailable,
  type CommandSpec,
} from '@/lib/harness/command-registry';
import {
  buildCommandPalette,
  type CommandPaletteSection,
} from '@/lib/harness/command-palette-model';
import { useCommandMemory, toggleCommandFavorite } from '@/lib/harness/command-history';
import { useProjectCommands } from '@/lib/harness/use-project-commands';

export { buildCommandPalette };
export type { CommandPaletteModel, CommandPaletteSection } from '@/lib/harness/command-palette-model';

export interface CommandPaletteAnchor {
  left: number;
  width: number;
  bottom: number;
}

/** The active-command chip above the composer (summary + availability). */
export function ActiveCommandBadge({ spec }: { spec: CommandSpec }) {
  const t = useT();
  const available = isCommandAvailable(spec);
  const summary = spec.summaryKey ? t(spec.summaryKey) : spec.summary;
  return (
    <div className="mb-2 flex items-center gap-1.5">
      <span
        className={cn(
          'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-medium',
          available
            ? 'border-primary/30 bg-primary/10 text-primary'
            : 'border-amber-400/30 bg-amber-400/10 text-amber-300',
        )}
      >
        <Command size={11} className="shrink-0" />
        {summary}
        {!available && (
          <span className="ml-1 text-[9px] uppercase tracking-wide opacity-80">not available</span>
        )}
      </span>
    </div>
  );
}

/** Reactive model for a composer token (`/`, `/sk`, …). Empty string = full catalog. */
export function useCommandPalette(query: string) {
  const { history, favorites } = useCommandMemory();
  const projectCommands = useProjectCommands();
  const token = useMemo(() => {
    const text = query.trimStart();
    if (!text.startsWith('/')) return null;
    const body = text.slice(1);
    if (/\s/.test(body)) return null; // past the command word
    return body.toLowerCase();
  }, [query]);

  const model = useMemo(
    () => buildCommandPalette(token ?? '', history.map((entry) => entry.name), favorites, projectCommands),
    [token, history, favorites, projectCommands],
  );

  const [highlight, setHighlight] = useState(0);
  useEffect(() => {
    setHighlight(0);
  }, [token]);

  useEffect(() => {
    if (highlight >= model.flat.length) setHighlight(0);
  }, [highlight, model.flat.length]);

  const listRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = listRef.current?.querySelector<HTMLElement>('[aria-selected="true"]');
    el?.scrollIntoView({ block: 'nearest' });
  }, [highlight, model.flat.length]);

  return {
    token,
    sections: model.sections,
    flat: model.flat,
    open: token !== null && model.flat.length > 0,
    highlight,
    setHighlight,
    listRef,
  };
}

function gateLabel(spec: CommandSpec): string {
  const gates = [
    spec.permissions.approval === 'operator' ? 'operator' : '',
    spec.risk === 'high' || spec.risk === 'critical' ? `${spec.risk} risk` : '',
  ].filter(Boolean);
  return gates.join(' · ');
}

function CommandRow({
  spec,
  index,
  active,
  showCategory,
  favorite,
  onHighlight,
  onSelect,
}: {
  spec: CommandSpec;
  index: number;
  active: boolean;
  showCategory: boolean;
  favorite: boolean;
  onHighlight: (index: number) => void;
  onSelect: (spec: CommandSpec) => void;
}) {
  const t = useT();
  const available = isCommandAvailable(spec);
  const hint = commandArgHint(spec);
  const gates = gateLabel(spec);
  const summary = spec.summaryKey ? t(spec.summaryKey) : spec.summary;
  return (
    <div
      id={`cmd-option-${index}`}
      role="option"
      aria-selected={active}
      aria-disabled={!available}
      tabIndex={-1}
      onMouseEnter={() => onHighlight(index)}
      // onMouseDown (not onClick) keeps the textarea from blurring first.
      onMouseDown={(e) => {
        e.preventDefault();
        onSelect(spec);
      }}
      className={cn(
        'group flex w-full cursor-default items-center gap-2 px-3 py-2 text-left text-sm transition-colors',
        active ? 'bg-accent/40' : 'hover:bg-accent/25',
        !available && 'opacity-60',
      )}
    >
      <Command size={13} className={cn('shrink-0', available ? 'text-primary' : 'text-amber-400/70')} />
      <span className="shrink-0 font-mono text-xs">/{spec.name}</span>
      {hint && (
        <span className="hidden shrink-0 font-mono text-[10px] text-muted-foreground/50 sm:inline">
          {hint}
        </span>
      )}
      <span className="ml-1 min-w-0 flex-1 truncate text-[11px] text-muted-foreground">
        {summary}
      </span>
      {showCategory && (
        <span className="hidden shrink-0 rounded-full bg-accent/30 px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-muted-foreground/60 sm:inline">
          {spec.category}
        </span>
      )}
      {spec.source === 'project' && (
        <span className="shrink-0 rounded-full bg-primary/10 px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-primary/80">
          project
        </span>
      )}
      {gates && (
        <span className="shrink-0 rounded-full bg-rose-400/10 px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-rose-300/80">
          {gates}
        </span>
      )}
      {!available && (
        <span className="shrink-0 text-[9px] uppercase tracking-wide text-amber-400/70">soon</span>
      )}
      <button
        type="button"
        aria-label={favorite ? 'Unpin command' : 'Pin command'}
        aria-pressed={favorite}
        title={favorite ? 'Unpin command' : 'Pin command'}
        onMouseDown={(e) => {
          e.preventDefault();
          e.stopPropagation();
          toggleCommandFavorite(spec.name);
        }}
        className={cn(
          'shrink-0 rounded-full p-1 transition-colors',
          favorite
            ? 'text-amber-300'
            : 'text-muted-foreground/30 opacity-0 hover:text-muted-foreground/70 group-hover:opacity-100',
        )}
      >
        <Star size={12} className={favorite ? 'fill-current' : undefined} />
      </button>
    </div>
  );
}

export interface CommandPaletteBodyProps {
  sections: readonly CommandPaletteSection[];
  flat: readonly CommandSpec[];
  highlight: number;
  query: string;
  favorites: readonly string[];
  layout: 'inline' | 'dialog';
  onHighlight: (index: number) => void;
  onSelect: (spec: CommandSpec) => void;
  listRef?: RefObject<HTMLDivElement | null>;
}

/** The list + detail body shared by the inline composer palette and the ⌘K dialog. */
export function CommandPaletteBody({
  sections,
  flat,
  highlight,
  query,
  favorites,
  layout,
  onHighlight,
  onSelect,
  listRef,
}: CommandPaletteBodyProps) {
  const t = useT();
  const active = flat[Math.min(Math.max(highlight, 0), Math.max(0, flat.length - 1))];
  const isDialog = layout === 'dialog';
  const favoriteSet = new Set(favorites);

  if (!flat.length) {
    return (
      <div className="px-4 py-8 text-center text-xs text-muted-foreground">
        {t('code.command.noMatches')}
      </div>
    );
  }

  const list = (
    <div
      ref={listRef}
      role="listbox"
      aria-label={t('code.command.paletteLabel')}
      aria-activedescendant={active ? `cmd-option-${Math.min(highlight, flat.length - 1)}` : undefined}
      className={cn('overflow-y-auto overscroll-contain', isDialog ? 'max-h-none' : 'max-h-[45vh]')}
    >
      {sections.map((section) => {
        if (!section.commands.length) return null;
        const firstIndex = flat.indexOf(section.commands[0]);
        return (
          <div key={section.key}>
            {section.title && (
              <div className="sticky top-0 z-[1] bg-background/90 px-3 pb-1 pt-2 text-[10px] uppercase tracking-wide text-muted-foreground/60 backdrop-blur">
                {section.titleKey ? t(section.titleKey) : section.title}
              </div>
            )}
            {section.commands.map((spec, i) => {
              const index = firstIndex + i;
              return (
                <CommandRow
                  key={spec.name}
                  spec={spec}
                  index={index}
                  active={index === highlight}
                  showCategory={Boolean(query.trim())}
                  favorite={favoriteSet.has(spec.name)}
                  onHighlight={onHighlight}
                  onSelect={onSelect}
                />
              );
            })}
          </div>
        );
      })}
    </div>
  );

  if (!isDialog) {
    return (
      <>
        {list}
        {active && (
          <div className="border-t border-white/5 px-3 py-2">
            <div className="line-clamp-2 text-[11px] leading-relaxed text-muted-foreground">
              {active.description}
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 font-mono text-[10px] text-muted-foreground/60">
              <span>
                /{active.name} {commandArgHint(active)}
              </span>
              {active.aliases.length > 0 && (
                <span className="text-muted-foreground/40">
                  {active.aliases.map((alias) => `/${alias}`).join(' · ')}
                </span>
              )}
            </div>
          </div>
        )}
      </>
    );
  }

  return (
    <div className="flex min-h-0 flex-1">
      <div className="flex min-h-0 min-w-0 flex-1 flex-col border-r border-white/5">{list}</div>
      <aside className="hidden min-h-0 w-72 shrink-0 flex-col gap-3 overflow-y-auto p-4 sm:flex">
        {active ? (
          <>
            <div>
              <div className="font-mono text-sm text-foreground">/{active.name}</div>
              <div className="mt-1 text-[10px] uppercase tracking-wide text-muted-foreground/50">
                {active.category} · {active.risk} risk · {active.permissions.approval ?? 'none'}
              </div>
            </div>
            <p className="text-xs leading-relaxed text-muted-foreground">{active.description}</p>
            <div className="rounded-lg bg-accent/20 p-2 font-mono text-[10px] text-muted-foreground">
              /{active.name}
              {commandArgHint(active) ? ` ${commandArgHint(active)}` : ''}
            </div>
            {active.aliases.length > 0 && (
              <div className="text-[11px] text-muted-foreground/70">
                <span className="text-muted-foreground/50">{t('code.command.aliases')}: </span>
                {active.aliases.map((alias) => `/${alias}`).join(', ')}
              </div>
            )}
            {active.examples.length > 0 && (
              <div className="text-[11px] text-muted-foreground/70">
                <div className="mb-1 text-muted-foreground/50">{t('code.command.examples')}</div>
                <ul className="space-y-1">
                  {active.examples.slice(0, 3).map((example) => (
                    <li key={example} className="truncate font-mono text-[10px] text-muted-foreground/80">
                      {example}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </>
        ) : null}
      </aside>
    </div>
  );
}

export interface CommandPaletteProps {
  anchor: CommandPaletteAnchor | null;
  open: boolean;
  query: string;
  sections: readonly CommandPaletteSection[];
  flat: readonly CommandSpec[];
  highlight: number;
  favorites: readonly string[];
  onHighlight: (index: number) => void;
  onSelect: (spec: CommandSpec) => void;
  listRef: RefObject<HTMLDivElement | null>;
}

/** The inline palette anchored above the composer. */
export function CommandPalette({
  anchor,
  open,
  query,
  sections,
  flat,
  highlight,
  favorites,
  onHighlight,
  onSelect,
  listRef,
}: CommandPaletteProps) {
  if (!open || !anchor || typeof document === 'undefined') return null;
  return createPortal(
    <div
      style={{ position: 'fixed', left: anchor.left, width: anchor.width, bottom: anchor.bottom }}
      className="z-[120] overflow-hidden rounded-2xl glass-command-popover shadow-lg"
    >
      <CommandPaletteBody
        sections={sections}
        flat={flat}
        highlight={highlight}
        query={query}
        favorites={favorites}
        layout="inline"
        onHighlight={onHighlight}
        onSelect={onSelect}
        listRef={listRef}
      />
    </div>,
    document.body,
  );
}

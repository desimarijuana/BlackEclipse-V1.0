'use client';

import { useEffect, useMemo, useState } from 'react';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { useKeyboardShortcutsStore } from '@/hooks/use-page-shortcuts';
import { canHandleKeyboardEvent, formatShortcutKeys, isKeyboardEventAvailable, isKeyboardScopeVisible } from '@/lib/keyboard';
import { useT, navLabelKey, type TranslationKey } from '@/lib/i18n';
import { DEFAULT_SIDEBAR_SECTIONS } from '@/lib/sidebar/config';
import { useHydrateSidebarConfig, useSidebarConfigStore } from '@/lib/sidebar/store';
import { useCommandStore } from '@/lib/search/store';
import {
  GLOBAL_SHORTCUTS,
  SHORTCUT_GROUP_LABEL_KEY,
  isHelpShortcut,
  isReservedSidebarShortcut,
  type ShortcutGroupId,
} from '@/lib/shortcuts';

interface HelpRow {
  id: string;
  label: string;
  keys: string;
  context: string;
  enabled: boolean;
  reserved?: boolean;
}

interface HelpGroup {
  id: string;
  label: string;
  current: boolean;
  rows: HelpRow[];
}

/** Platform-aware label: the catalogue stores a neutral “Ctrl / Cmd”, which
 *  reads as a lie on a Mac. Resolved client-side so SSR stays stable. */
function platformKeys(keys: string, isMac: boolean): string {
  return isMac ? keys.replace(/Ctrl \/ Cmd/g, '⌘') : keys.replace(/Ctrl \/ Cmd/g, 'Ctrl');
}

export function KeyboardShortcuts() {
  useHydrateSidebarConfig();
  const t = useT();
  const config = useSidebarConfigStore((state) => state.config);
  const { scopes, helpOpen, setHelpOpen } = useKeyboardShortcutsStore();
  const searchOpen = useCommandStore((state) => state.open);
  const [query, setQuery] = useState('');
  const [currentScopes, setCurrentScopes] = useState<readonly symbol[]>([]);
  const [isMac, setIsMac] = useState(false);

  useEffect(() => {
    const platform = typeof navigator !== 'undefined' ? `${navigator.platform} ${navigator.userAgent}` : '';
    setIsMac(/mac|iphone|ipad/i.test(platform));
  }, []);

  useEffect(() => {
    const unsubscribe = useCommandStore.subscribe((state) => {
      if (state.open) useKeyboardShortcutsStore.getState().setHelpOpen(false);
    });
    const onKeyDown = (event: KeyboardEvent) => {
      if (!isHelpShortcut(event) || !isKeyboardEventAvailable(event)) return;
      const state = useKeyboardShortcutsStore.getState();
      if (state.helpOpen) {
        // Plain `?` must be able to type into the dialog's search field; only
        // the explicit Ctrl/Cmd + / chord closes an already-open dialog.
        if (!event.ctrlKey && !event.metaKey) return;
        event.preventDefault();
        state.setHelpOpen(false);
        return;
      }
      if (useCommandStore.getState().open || !canHandleKeyboardEvent(event)) return;
      event.preventDefault();
      setQuery('');
      setCurrentScopes(state.scopes.filter((scope) => isKeyboardScopeVisible(scope.rootRef.current)).map((scope) => scope.token));
      state.setHelpOpen(true);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => {
      unsubscribe();
      window.removeEventListener('keydown', onKeyDown);
    };
  }, []);

  const groups = useMemo<HelpGroup[]>(() => {
    const globalGroups: ShortcutGroupId[] = ['essentials', 'navigation', 'chart'];
    const global = globalGroups.map((group) => ({
      id: group,
      label: t(SHORTCUT_GROUP_LABEL_KEY[group] as TranslationKey),
      current: false,
      rows: GLOBAL_SHORTCUTS.filter((s) => s.group === group).map((s) => ({
        id: s.id,
        label: s.label,
        keys: platformKeys(s.keys, isMac),
        context: s.context,
        enabled: true,
        reserved: s.reserved,
      })),
    }));

    const sidebar: HelpGroup = {
      id: 'sidebar-navigation',
      label: t('keyboard.sidebarNavGroup'),
      current: false,
      rows: config.sections.map((section) => {
        const key = navLabelKey(section.id);
        return {
          id: section.id,
          label: key ? t(key) : (DEFAULT_SIDEBAR_SECTIONS.find((item) => item.id === section.id)?.label ?? section.id),
          keys: section.shortcut || t('common.none'),
          context: section.enabled
            ? t('keyboard.customizeHint')
            : 'Hidden from the sidebar, so its shortcut cannot open it.',
          enabled: section.enabled && Boolean(section.shortcut),
          reserved: Boolean(section.shortcut) && isReservedSidebarShortcut(section.shortcut),
        };
      }),
    };

    const pageGroups: HelpGroup[] = scopes.map((scope, index) => ({
      id: `scope-${index}`,
      label: scope.rootRef.current?.getAttribute('data-keyboard-scope') || scope.rootRef.current?.id || `Page shortcuts ${index + 1}`,
      current: currentScopes.includes(scope.token),
      rows: scope.actionsRef.current.map((action) => ({
        ...action,
        keys: platformKeys(formatShortcutKeys(action.keys), isMac),
        context: 'Visible page scope, not while typing',
        enabled: action.enabled !== false,
      })),
    }));

    return [...global, sidebar, ...pageGroups];
  }, [config.sections, currentScopes, isMac, scopes, t]);

  const filter = query.trim().toLowerCase();
  const visibleGroups = groups
    .map((group) => ({
      ...group,
      rows: group.rows.filter((row) =>
        `${group.label} ${row.label} ${row.keys} ${row.context}`.toLowerCase().includes(filter),
      ),
    }))
    .filter((group) => group.rows.length > 0);

  const hasReserved = groups.some((group) => group.rows.some((row) => row.reserved && row.enabled));

  return (
    <Dialog open={helpOpen && !searchOpen} onOpenChange={setHelpOpen}>
      <DialogContent className="glass-card-strong grid-rows-[auto_auto_auto_minmax(0,1fr)_auto] rounded-xl sm:max-w-2xl max-h-[85dvh] overflow-hidden">
        <DialogTitle className="pr-8">{t('keyboard.title')}</DialogTitle>
        <DialogDescription>
          Page shortcuts use the visible scope; focused nested scopes take priority. Shortcuts pause while typing or behind dialogs.
        </DialogDescription>
        <input
          autoFocus
          aria-label={t('keyboard.searchPlaceholder')}
          placeholder={t('keyboard.searchPlaceholder')}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className="w-full rounded-md border border-border bg-background/60 px-3 py-2 outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
        <div className="min-h-0 overflow-y-auto overscroll-contain pr-2 space-y-5" tabIndex={0} aria-label="Shortcut results">
          {visibleGroups.length === 0 && <p className="text-muted-foreground" role="status">{t('keyboard.noMatches')}</p>}
          {visibleGroups.map((group) => (
            <section key={group.id} aria-label={group.label}>
              <h2 className="mb-2 text-sm font-medium">
                {group.label}{group.current && <span className="ml-2 text-xs text-primary">Current</span>}
              </h2>
              <ul className="space-y-1">
                {group.rows.map((row) => (
                  <li key={row.id} className="glass-card-subtle flex items-center justify-between gap-4 rounded-md px-3 py-2">
                    <div className="min-w-0">
                      <p>
                        {row.label}
                        {!row.enabled && <span className="ml-2 text-xs text-muted-foreground">Unavailable</span>}
                        {row.reserved && row.enabled && (
                          <span
                            className="ml-2 rounded-full border border-amber-500/40 bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-medium text-amber-500"
                            title={t('keyboard.reservedHint')}
                          >
                            {t('keyboard.reservedHint')}
                          </span>
                        )}
                      </p>
                      <p className="text-xs text-muted-foreground">{row.context}</p>
                    </div>
                    <kbd className="shrink-0 rounded border border-border px-2 py-1 text-xs">{row.keys}</kbd>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
        <div className="space-y-1 text-xs text-muted-foreground">
          {hasReserved && <p>{t('keyboard.reservedNote')}</p>}
          <p>
            Some keyboards require Fn for function keys. Browser and OS reserved keys may take priority. Ctrl shortcuts also accept Cmd on Mac.
          </p>
        </div>
      </DialogContent>
    </Dialog>
  );
}

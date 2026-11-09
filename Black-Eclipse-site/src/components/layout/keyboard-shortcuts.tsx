'use client';

import { useEffect, useState } from 'react';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { useKeyboardShortcutsStore } from '@/hooks/use-page-shortcuts';
import { canHandleKeyboardEvent, formatShortcutKeys, isKeyboardEventAvailable, isKeyboardScopeVisible, matchesShortcut } from '@/lib/keyboard';
import { DEFAULT_SIDEBAR_SECTIONS } from '@/lib/sidebar/config';
import { useHydrateSidebarConfig, useSidebarConfigStore } from '@/lib/sidebar/store';
import { useCommandStore } from '@/lib/search/store';
import { useT, navLabelKey } from '@/lib/i18n';

const GLOBAL_SHORTCUTS = [
  { id: 'help', label: 'Toggle keyboard shortcuts', keys: 'Ctrl / Cmd + /', context: 'Global, outside other dialogs' },
  { id: 'search', label: 'Toggle global search', keys: 'Ctrl / Cmd + K', context: 'Global, outside other dialogs' },
  { id: 'focus-chat', label: 'Focus the chat composer', keys: '/', context: 'Global, not while typing' },
  { id: 'chat-new', label: 'New chat', keys: 'Ctrl / Cmd + Alt + N', context: 'Global, switches to the Eclipse Agent page and starts a new chat' },
  { id: 'mode-terminal', label: 'Sidebar menu: Terminal', keys: 'Alt + T', context: 'Global, switches the sidebar menu mode' },
  { id: 'mode-agentic', label: 'Sidebar menu: Agentic', keys: 'Alt + A', context: 'Global, switches the sidebar menu mode' },
  { id: 'mode-bots', label: 'Sidebar menu: Bots', keys: 'Alt + B', context: 'Global, switches the sidebar menu mode and opens the Bots workspace' },
  { id: 'mode-graph', label: 'Sidebar menu: Graph Studio', keys: 'Alt + G', context: 'Global, switches the sidebar menu mode and opens Overview' },
  { id: 'terminal', label: 'Toggle visible terminal', keys: 'Ctrl / Cmd + `', context: 'Global' },
  { id: 'workspace', label: 'Toggle Agent Workspace sidebar', keys: 'Ctrl / Cmd + Shift + E', context: 'Global, not while typing' },
  { id: 'focus-mode', label: 'Toggle focus mode (chat)', keys: 'Ctrl + Alt + X', context: 'Eclipse Agent tab, hides header and sidebar for a full-width focus view' },
  { id: 'chart-cancel', label: 'Cancel drawing / cursor tool', keys: 'Escape', context: 'Active chart drawing tools' },
  { id: 'chart-delete', label: 'Delete selected drawing', keys: 'Delete / Backspace', context: 'Active chart with a selected drawing' },
  { id: 'chart-undo', label: 'Undo drawing', keys: 'Ctrl / Cmd + Z', context: 'Active chart drawing history' },
  { id: 'chart-redo', label: 'Redo drawing', keys: 'Ctrl / Cmd + Shift + Z', context: 'Active chart drawing history' },
];

export function KeyboardShortcuts() {
  useHydrateSidebarConfig();
  const t = useT();
  const config = useSidebarConfigStore((state) => state.config);
  const { scopes, helpOpen, setHelpOpen } = useKeyboardShortcutsStore();
  const searchOpen = useCommandStore((state) => state.open);
  const [query, setQuery] = useState('');
  const [currentScopes, setCurrentScopes] = useState<readonly symbol[]>([]);

  useEffect(() => {
    const unsubscribe = useCommandStore.subscribe((state) => {
      if (state.open) useKeyboardShortcutsStore.getState().setHelpOpen(false);
    });
    const onKeyDown = (event: KeyboardEvent) => {
      if (!matchesShortcut(event, 'mod+/') || !isKeyboardEventAvailable(event)) return;
      const state = useKeyboardShortcutsStore.getState();
      if (state.helpOpen) {
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

  const filter = query.trim().toLowerCase();
  const groups = [
    {
      id: 'global', label: 'Global and chart shortcuts', current: false,
      rows: GLOBAL_SHORTCUTS.map((shortcut) => ({ ...shortcut, enabled: true })),
    },
    {
      id: 'navigation', label: 'Sidebar navigation', current: false,
      rows: config.sections.map((section) => {
        const key = navLabelKey(section.id);
        return {
          id: section.id,
          label: key ? t(key) : (DEFAULT_SIDEBAR_SECTIONS.find((item) => item.id === section.id)?.label ?? section.id),
          keys: section.shortcut ? formatShortcutKeys(section.shortcut) : t('common.none'),
          context: 'Main application sidebar; assignments editable in Settings',
          enabled: section.enabled && Boolean(section.shortcut),
        };
      }),
    },
    ...scopes.map((scope, index) => ({
      id: `scope-${index}`,
      label: scope.rootRef.current?.getAttribute('data-keyboard-scope') || scope.rootRef.current?.id || `Page shortcuts ${index + 1}`,
      current: currentScopes.includes(scope.token),
      rows: scope.actionsRef.current.map((action) => ({
        ...action,
        keys: formatShortcutKeys(action.keys),
        context: 'Visible page scope, not while typing',
        enabled: action.enabled !== false,
      })),
    })),
  ].map((group) => ({ ...group, rows: group.rows.filter((row) => `${group.label} ${row.label} ${row.keys} ${row.context}`.toLowerCase().includes(filter)) })).filter((group) => group.rows.length > 0);

  return (
    <Dialog open={helpOpen && !searchOpen} onOpenChange={setHelpOpen}>
      <DialogContent className="glass-card-strong grid-rows-[auto_auto_auto_minmax(0,1fr)_auto] rounded-xl sm:max-w-2xl max-h-[85dvh] overflow-hidden">
        <DialogTitle className="pr-8">{t('keyboard.title')}</DialogTitle>
        <DialogDescription>
          Page shortcuts use the visible scope; focused nested scopes take priority. Shortcuts pause while typing or behind dialogs.
        </DialogDescription>
        <input
          aria-label={t('keyboard.searchPlaceholder')}
          placeholder={t('keyboard.searchPlaceholder')}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className="w-full rounded-md border border-border bg-background/60 px-3 py-2 outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
        <div className="min-h-0 overflow-y-auto overscroll-contain pr-2 space-y-5" tabIndex={0} aria-label="Shortcut results">
          {groups.length === 0 && <p className="text-muted-foreground" role="status">{t('keyboard.noMatches')}</p>}
          {groups.map((group) => (
            <section key={group.id} aria-label={group.label}>
              <h2 className="mb-2 text-sm font-medium">
                {group.label}{group.current && <span className="ml-2 text-xs text-primary">Current</span>}
              </h2>
              <ul className="space-y-1">
                {group.rows.map((row) => (
                  <li key={row.id} className="glass-card-subtle flex items-center justify-between gap-4 rounded-md px-3 py-2">
                    <div>
                      <p>{row.label}{!row.enabled && <span className="ml-2 text-xs text-muted-foreground">Unavailable</span>}</p>
                      <p className="text-xs text-muted-foreground">{row.context}</p>
                    </div>
                    {/* Rows are already display-formatted at build time (sidebar
                        rows use formatShortcutKeys, scope rows too, global rows
                        are human strings). Formatting twice uppercased labels
                        like "Shift + E" into "SHIFT + E". */}
                    <kbd className="shrink-0 rounded border border-border px-2 py-1 text-xs">{row.keys}</kbd>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
        <p className="text-xs text-muted-foreground">
          Some keyboards require Fn for function keys. Browser and OS reserved keys may take priority; F11 is reserved for fullscreen by default. Ctrl shortcuts also accept Cmd on Mac.
        </p>
      </DialogContent>
    </Dialog>
  );
}

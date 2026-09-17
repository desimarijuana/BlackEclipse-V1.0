'use client';

import { useCallback, useEffect, useRef, useState, type RefObject } from 'react';
import { usePageShortcuts, type PageShortcut } from '@/hooks/use-page-shortcuts';

export type ListNavigationAction = 'next' | 'prev' | 'first' | 'last';

export interface ListNavigationPagination {
  onPrevious: () => void;
  onNext: () => void;
  canPrevious?: boolean;
  canNext?: boolean;
}

export interface ListNavigationOptions {
  ids: readonly string[];
  rootRef: RefObject<HTMLElement | null>;
  onOpen?: (id: string) => void;
  onSelectionChange?: (id: string | null) => void;
  onEscape?: (id: string | null) => void;
  pagination?: ListNavigationPagination;
  enabled?: boolean;
  shortcutPrefix?: string;
}

export type ListNavigationRowAttributes = {
  'data-list-id': string;
};

export interface ListNavigation {
  selectedId: string | null;
  select: (id: string | null) => void;
  isSelected: (id: string) => boolean;
  rowAttributes: (id: string) => ListNavigationRowAttributes;
}

export function nextListId(
  ids: readonly string[],
  currentId: string | null,
  action: ListNavigationAction,
): string | null {
  if (ids.length === 0) return null;
  if (action === 'first') return ids[0];
  if (action === 'last') return ids[ids.length - 1];
  const index = currentId === null ? -1 : ids.indexOf(currentId);
  if (index === -1) return action === 'next' ? ids[0] : ids[ids.length - 1];
  const delta = action === 'next' ? 1 : -1;
  return ids[(index + delta + ids.length) % ids.length];
}

function rowSelector(id: string): string {
  return `[data-list-id="${id.replace(/["\\]/g, '\\$&')}"]`;
}

export function useListNavigation(options: ListNavigationOptions): ListNavigation {
  const { ids, rootRef, enabled = true, shortcutPrefix = 'list' } = options;
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const stateRef = useRef({
    ids,
    selectedId,
    onOpen: options.onOpen,
    onEscape: options.onEscape,
    pagination: options.pagination,
  });
  useEffect(() => {
    stateRef.current = {
      ids,
      selectedId,
      onOpen: options.onOpen,
      onEscape: options.onEscape,
      pagination: options.pagination,
    };
  });

  const notifyRef = useRef(options.onSelectionChange);
  useEffect(() => {
    notifyRef.current = options.onSelectionChange;
  });

  const select = useCallback((id: string | null) => {
    if (stateRef.current.selectedId === id) return;
    stateRef.current.selectedId = id;
    setSelectedId(id);
  }, []);

  useEffect(() => {
    notifyRef.current?.(selectedId);
  }, [selectedId]);

  const findRow = useCallback(
    (id: string) => rootRef.current?.querySelector<HTMLElement>(rowSelector(id)) ?? null,
    [rootRef],
  );

  useEffect(() => {
    if (!selectedId) return;
    findRow(selectedId)?.scrollIntoView?.({ block: 'nearest' });
  }, [selectedId, findRow]);

  const move = useCallback(
    (action: ListNavigationAction) => {
      select(nextListId(stateRef.current.ids, stateRef.current.selectedId, action));
    },
    [select],
  );

  const open = useCallback((id: string) => {
    stateRef.current.onOpen?.(id);
  }, []);

  const clearAndRestoreFocus = useCallback(() => {
    const id = stateRef.current.selectedId;
    select(null);
    const row = id ? findRow(id) : null;
    if (row) {
      if (row.tabIndex < 0) row.tabIndex = -1;
      row.focus?.();
    }
    stateRef.current.onEscape?.(id);
  }, [findRow, select]);

  const pagination = options.pagination;
  const actions: PageShortcut[] = [
    { id: `${shortcutPrefix}.next`, label: 'Next row', keys: 'ArrowDown', run: () => move('next'), enabled },
    { id: `${shortcutPrefix}.next-alias`, label: 'Next row', keys: 'J', run: () => move('next'), enabled },
    { id: `${shortcutPrefix}.prev`, label: 'Previous row', keys: 'ArrowUp', run: () => move('prev'), enabled },
    { id: `${shortcutPrefix}.prev-alias`, label: 'Previous row', keys: 'K', run: () => move('prev'), enabled },
    { id: `${shortcutPrefix}.first`, label: 'First row', keys: 'Home', run: () => move('first'), enabled },
    { id: `${shortcutPrefix}.last`, label: 'Last row', keys: 'End', run: () => move('last'), enabled },
    {
      id: `${shortcutPrefix}.open`,
      label: 'Open selected row',
      keys: 'Enter',
      run: () => {
        const id = stateRef.current.selectedId;
        if (id) open(id);
      },
      enabled: enabled && selectedId !== null,
    },
    {
      id: `${shortcutPrefix}.clear`,
      label: 'Clear row selection',
      keys: 'Escape',
      run: clearAndRestoreFocus,
      enabled: enabled && selectedId !== null,
    },
  ];
  if (pagination) {
    actions.push(
      {
        id: `${shortcutPrefix}.prev-page`,
        label: 'Previous page',
        keys: '[',
        run: () => pagination.onPrevious(),
        enabled: enabled && pagination.canPrevious !== false,
      },
      {
        id: `${shortcutPrefix}.next-page`,
        label: 'Next page',
        keys: ']',
        run: () => pagination.onNext(),
        enabled: enabled && pagination.canNext !== false,
      },
    );
  }
  usePageShortcuts(rootRef, actions);

  const isSelected = useCallback((id: string) => selectedId === id, [selectedId]);
  const rowAttributes = useCallback(
    (id: string): ListNavigationRowAttributes => ({ 'data-list-id': id }),
    [],
  );

  return { selectedId, select, isSelected, rowAttributes };
}

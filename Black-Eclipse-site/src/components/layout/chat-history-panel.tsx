"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { confirmDialog } from '@/lib/ui/confirm-dialog';
import {
  Check,
  ChevronDown,
  Clock,
  Folder,
  FolderOpen,
  FolderPlus,
  GitBranch,
  ListChecks,
  Loader2,
  MoreHorizontal,
  Pin,
  PinOff,
  Plus,
  Search,
  Trash2,
  X,
} from '@/lib/icons';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  buildChatHistoryView,
  collectTags,
  scoreConversation,
  type ChatDateBucket,
  type ChatFolder,
  type ChatGroupMode,
  type ChatOrganizationApi,
  type ChatSortMode,
  type Conversation,
} from '@/lib/chat/chat-organization';
import { ChatHistoryMenu, type MenuAnchor } from '@/components/layout/chat-history-menu';

export interface ChatHistoryPanelProps {
  conversations: Conversation[];
  organization: ChatOrganizationApi;
  activeConversationId: string | null;
  onSelectConversation: (id: string) => void;
  onNewChat: () => void;
  /** Copy a chat into a new conversation (its own transcript + session). */
  onForkConversation: (id: string) => void;
  /** Legacy permanent delete (also fixes the active selection in the shell). */
  onDeleteConversation: (id: string) => void;
  /** Conversations with a live run (parallel sessions show a spinner). */
  runningConversationIds?: string[];
  /** Waiting prompt count per conversation. */
  queuedCounts?: Record<string, number>;
}

type RenameTarget = { kind: 'chat' | 'folder'; id: string } | null;

/** Persisted grouping preference (Date vs Folders). */
const GROUP_MODE_STORAGE_KEY = 'chat_group_by_v1';
/** Sentinel value for the tag filter's "All" option (base-ui dislikes ""). */
const ALL_TAGS = '__all__';

export function ChatHistoryPanel({
  conversations,
  organization,
  activeConversationId,
  onSelectConversation,
  onNewChat,
  onForkConversation,
  onDeleteConversation,
  runningConversationIds = [],
  queuedCounts = {},
}: ChatHistoryPanelProps) {
  const t = useT();
  const {
    folders, createFolder: onCreateFolder, renameFolder: onRenameFolder, deleteFolder: onDeleteFolder,
    toggleFolder: onToggleFolder, setFolderColor: onSetFolderColor, moveFolder: onMoveFolder,
    moveConversation: onMoveConversation, setConversationColor: onSetConversationColor, togglePin: onTogglePin,
    renameConversation: onRenameConversation, addTag: onAddTag, removeTag: onRemoveTag, bulkPin,
  } = organization;

  const [query, setQuery] = useState('');
  const [sort, setSort] = useState<ChatSortMode>('recent');
  const [groupBy, setGroupBy] = useState<ChatGroupMode>('date');
  const [tagFilter, setTagFilter] = useState<string>('');
  const [menu, setMenu] = useState<MenuAnchor | null>(null);
  const [renaming, setRenaming] = useState<RenameTarget>(null);
  const [dropKey, setDropKey] = useState<string | null>(null);
  // Multi-select: when on, clicking rows toggles them instead of opening them.
  const [selecting, setSelecting] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [anchorId, setAnchorId] = useState<string | null>(null);
  const [ghost, setGhost] = useState<{ x: number; y: number; label: string } | null>(null);
  const dragRef = useRef<{ id: string; kind: 'chat' | 'folder'; startX: number; startY: number; active: boolean; label: string } | null>(null);
  const didDragRef = useRef(false);

  // Restore the persisted grouping preference once mounted (SSR-safe), then save.
  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(GROUP_MODE_STORAGE_KEY);
      if (stored === 'date' || stored === 'folders') setGroupBy(stored);
    } catch {
      /* private mode: keep the default */
    }
  }, []);
  useEffect(() => {
    try {
      window.localStorage.setItem(GROUP_MODE_STORAGE_KEY, groupBy);
    } catch {
      /* private mode: preference is best-effort */
    }
  }, [groupBy]);

  const view = useMemo(
    () => buildChatHistoryView(conversations, folders, { query, sort, scope: 'active', tag: tagFilter || null, groupBy }),
    [conversations, folders, query, sort, tagFilter, groupBy],
  );
  const bucketLabel = useMemo(
    (): Record<ChatDateBucket, string> => ({
      today: t('sidebar.dateToday'),
      yesterday: t('sidebar.dateYesterday'),
      week: t('sidebar.dateWeek'),
      month: t('sidebar.dateMonth'),
      older: t('sidebar.dateOlder'),
    }),
    [t],
  );
  const sortOptions = useMemo(
    (): { value: ChatSortMode; label: string }[] => [
      { value: 'recent', label: t('sidebar.sortRecent') },
      { value: 'created', label: t('sidebar.sortCreated') },
      { value: 'alpha', label: t('sidebar.sortAlpha') },
    ],
    [t],
  );
  const tags = useMemo(() => collectTags(conversations), [conversations]);
  const tagOptions = useMemo(
    (): { value: string; label: string }[] => [
      { value: ALL_TAGS, label: t('sidebar.allTags') },
      ...tags.map((tag) => ({ value: tag, label: tag })),
    ],
    [tags, t],
  );
  const snippets = useMemo(() => {
    if (!query.trim()) return null;
    const map = new Map<string, string | null>();
    for (const c of conversations) map.set(c.id, scoreConversation(c, query)?.snippet ?? null);
    return map;
  }, [conversations, query]);

  // Every row currently on screen, in render order — the selection surface.
  const visibleIds = useMemo(
    () => [...view.pinned, ...view.groups.flatMap((g) => g.conversations)].map((c) => c.id),
    [view],
  );

  const exitSelection = useCallback(() => {
    setSelecting(false);
    setSelectedIds(new Set());
    setAnchorId(null);
  }, []);

  // Drop ids that were deleted elsewhere so the count never lies.
  useEffect(() => {
    setSelectedIds((prev) => {
      if (prev.size === 0) return prev;
      const live = new Set(conversations.map((c) => c.id));
      const next = new Set([...prev].filter((id) => live.has(id)));
      return next.size === prev.size ? prev : next;
    });
  }, [conversations]);

  // Escape leaves selection mode (without touching any chat).
  useEffect(() => {
    if (!selecting) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') exitSelection();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [selecting, exitSelection]);

  const toggleSelect = (id: string, e: React.MouseEvent) => {
    if (e.shiftKey && anchorId && anchorId !== id) {
      const from = visibleIds.indexOf(anchorId);
      const to = visibleIds.indexOf(id);
      if (from !== -1 && to !== -1) {
        const [lo, hi] = from < to ? [from, to] : [to, from];
        setSelectedIds((prev) => {
          const next = new Set(prev);
          for (let i = lo; i <= hi; i++) next.add(visibleIds[i]);
          return next;
        });
        return;
      }
    }
    setAnchorId(id);
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectAll = () => {
    setSelectedIds(new Set(visibleIds));
    setAnchorId(visibleIds[visibleIds.length - 1] ?? null);
  };

  const selectNone = () => {
    setSelectedIds(new Set());
    setAnchorId(null);
  };

  const pinSelected = () => {
    const ids = [...selectedIds];
    if (ids.length === 0) return;
    const allPinned = ids.every((id) => conversations.find((c) => c.id === id)?.pinned);
    bulkPin(ids, !allPinned);
  };

  const deleteSelected = async () => {
    const ids = [...selectedIds];
    if (ids.length === 0) return;
    const confirmed = await confirmDialog({
      title: ids.length === 1
        ? t('sidebar.confirmDeleteForever')
        : t('sidebar.confirmDeleteMany', { count: ids.length }),
      tone: 'danger',
    });
    if (!confirmed) return;
    for (const id of ids) onDeleteConversation(id);
    exitSelection();
  };

  // ── Drag & drop (pointer-based, so it works with mouse and touch) ───────────
  const performDrop = (kind: 'chat' | 'folder', id: string, key: string) => {
    if (kind === 'chat') {
      if (key === 'pinned') bulkPin([id], true);
      else if (key === 'unfiled') onMoveConversation(id, null);
      else if (key.startsWith('folder:')) onMoveConversation(id, key.slice(7));
    } else {
      if (key === 'root') onMoveFolder(id, null, null);
      else if (key.startsWith('folder:')) onMoveFolder(id, key.slice(7), null);
    }
  };

  const beginDrag = (e: React.PointerEvent, id: string, kind: 'chat' | 'folder', label: string) => {
    if (e.pointerType === 'mouse' && e.button !== 0) return;
    if ((e.target as HTMLElement).closest('[data-no-drag]')) return;
    dragRef.current = { id, kind, startX: e.clientX, startY: e.clientY, active: false, label };
    const onMove = (ev: PointerEvent) => {
      const st = dragRef.current;
      if (!st) return;
      if (!st.active) {
        if (Math.hypot(ev.clientX - st.startX, ev.clientY - st.startY) < 6) return;
        st.active = true;
        didDragRef.current = true;
        document.body.style.userSelect = 'none';
      }
      setGhost({ x: ev.clientX, y: ev.clientY, label: st.label });
      const el = document.elementFromPoint(ev.clientX, ev.clientY) as HTMLElement | null;
      setDropKey(el?.closest('[data-droppable]')?.getAttribute('data-drop-key') ?? null);
    };
    const finish = (ev: PointerEvent) => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', finish);
      window.removeEventListener('pointercancel', finish);
      document.body.style.userSelect = '';
      const st = dragRef.current;
      dragRef.current = null;
      const el = document.elementFromPoint(ev.clientX, ev.clientY) as HTMLElement | null;
      const key = el?.closest('[data-droppable]')?.getAttribute('data-drop-key') ?? null;
      setGhost(null);
      setDropKey(null);
      if (st?.active && key) performDrop(st.kind, st.id, key);
      setTimeout(() => { didDragRef.current = false; }, 0);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', finish);
    window.addEventListener('pointercancel', finish);
  };

  // ── Actions ────────────────────────────────────────────────────────────────
  const openMenu = (e: React.MouseEvent, kind: 'chat' | 'folder', id: string) => {
    e.stopPropagation();
    const r = e.currentTarget.getBoundingClientRect();
    setMenu({ kind, id, x: r.right, y: r.bottom, up: r.bottom > window.innerHeight - 320 });
    setRenaming(null);
  };

  const commitRename = (target: RenameTarget, value: string) => {
    const trimmed = value.trim();
    if (target && trimmed) {
      if (target.kind === 'chat') onRenameConversation(target.id, trimmed);
      else onRenameFolder(target.id, trimmed);
    }
    setRenaming(null);
  };

  const renameInput = (target: RenameTarget, initial: string) => (
    <input
      autoFocus
      defaultValue={initial}
      onClick={(e) => e.stopPropagation()}
      onPointerDown={(e) => e.stopPropagation()}
      onBlur={(e) => commitRename(target, e.target.value)}
      onKeyDown={(e) => {
        if (e.key === 'Enter') commitRename(target, (e.target as HTMLInputElement).value);
        if (e.key === 'Escape') setRenaming(null);
      }}
      className="w-full min-w-0 rounded-md border border-border/50 bg-background/60 px-1.5 py-0.5 text-[12px] text-foreground outline-none focus:border-border"
    />
  );

  // ── Rows ───────────────────────────────────────────────────────────────────
  const running = new Set(runningConversationIds);
  const renderRow = (c: Conversation, depth = 0) => {
    const isActive = activeConversationId === c.id;
    const isRunning = running.has(c.id);
    const queuedCount = queuedCounts[c.id] ?? 0;
    const isRenaming = renaming?.kind === 'chat' && renaming.id === c.id;
    const snippet = snippets?.get(c.id) ?? null;
    const isSelected = selectedIds.has(c.id);
    return (
      <div key={c.id} style={{ paddingLeft: depth * 12 }}>
        <div
          onClick={(e) => {
            if (didDragRef.current) return;
            if (selecting) {
              if (!isRenaming) toggleSelect(c.id, e);
              return;
            }
            if (!isRenaming) onSelectConversation(c.id);
          }}
          onPointerDown={(e) => !selecting && !isRenaming && beginDrag(e, c.id, 'chat', c.title || t('sidebar.untitledSession'))}
          role={selecting ? 'checkbox' : undefined}
          aria-checked={selecting ? isSelected : undefined}
          className={`flex items-center justify-between gap-1 rounded-xl px-2.5 py-1.5 text-[11px] cursor-pointer group transition-all border ${
            ghost && dragRef.current?.id === c.id && dragRef.current?.active ? 'opacity-40' : ''
          } ${
            isSelected ? 'bg-primary/10 border-primary/30 text-foreground'
              : isActive ? 'bg-white/[0.04] border-border/20 text-foreground font-semibold'
                : 'bg-transparent border-transparent text-foreground/70 hover:bg-accent/25 hover:text-foreground'
          }`}
        >
          {selecting && (
            <span
              aria-hidden
              className={`flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-[4px] border transition-colors ${
                isSelected ? 'border-primary bg-primary text-primary-foreground' : 'border-border/60 text-transparent'
              }`}
            >
              <Check size={10} weight="bold" />
            </span>
          )}
          <span className="flex items-center gap-1.5 min-w-0 flex-1">
            {c.pinned && <Pin size={10} className="shrink-0 text-amber-400" weight="fill" />}
            {c.forkedFrom && (
              <span title={`Forked from ${c.forkedFrom.title || 'another chat'}`} className="shrink-0">
                <GitBranch size={10} className="text-primary/70" />
              </span>
            )}
            {c.color && <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: c.color }} />}
            <span className="min-w-0 flex-1">
              {isRenaming ? renameInput(renaming, c.title) : <span className="block truncate">{c.title || t('sidebar.untitledSession')}</span>}
              {snippet && !isRenaming && <span className="block truncate text-[10px] font-normal text-muted-foreground">{snippet}</span>}
            </span>
          </span>
          {isRunning && (
            <span
              className="shrink-0 text-primary"
              title={t('sidebar.running')}
              aria-label={t('sidebar.running')}
            >
              <Loader2 size={11} className="animate-spin" />
            </span>
          )}
          {queuedCount > 0 && (
            <span
              className="inline-flex shrink-0 items-center gap-0.5 rounded bg-primary/10 px-1 text-[9px] font-semibold text-primary"
              title={`${queuedCount} queued`}
              aria-label={`${queuedCount} queued`}
            >
              <ListChecks size={10} />
              {queuedCount}
            </span>
          )}
          {!isRenaming && (c.tags?.length ?? 0) > 0 && (
            <span className="shrink-0 rounded bg-white/[0.06] px-1 text-[9px] text-muted-foreground">{c.tags!.length}</span>
          )}
          {!isRenaming && !selecting && (
            <button
              onClick={(e) => openMenu(e, 'chat', c.id)}
              data-no-drag
              className={`shrink-0 rounded p-0.5 hover:text-foreground transition-opacity ${
                menu?.kind === 'chat' && menu.id === c.id ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
              }`}
              title={t('sidebar.chatOptions')}
            >
              <MoreHorizontal size={13} />
            </button>
          )}
        </div>
      </div>
    );
  };

  const renderGroupHeader = (folder: ChatFolder | null, count: number, depth: number) => {
    const isFolder = folder !== null;
    const isRenaming = isFolder && renaming?.kind === 'folder' && renaming.id === folder.id;
    const collapsed = isFolder && folder.collapsed;
    return (
      <div
        className="flex items-center justify-between gap-1 px-1 group rounded-lg"
        style={{ paddingLeft: 4 + depth * 12 }}
        onPointerDown={(e) => isFolder && !isRenaming && beginDrag(e, folder.id, 'folder', folder.name)}
      >
        <button
          onClick={() => { if (didDragRef.current) return; if (isFolder) onToggleFolder(folder.id); }}
          className="flex items-center gap-1.5 min-w-0 flex-1 text-left cursor-pointer"
        >
          {isFolder && <ChevronDown size={11} className={`shrink-0 text-muted-foreground transition-transform ${collapsed ? '-rotate-90' : ''}`} />}
          {isFolder ? (
            collapsed ? <Folder size={12} className="shrink-0" style={{ color: folder.color }} />
              : <FolderOpen size={12} className="shrink-0" style={{ color: folder.color }} />
          ) : (
            <Folder size={12} className="shrink-0 text-muted-foreground" />
          )}
          {isRenaming ? renameInput(renaming, folder.name) : (
            <span className="truncate text-[11px] font-bold uppercase tracking-wider text-muted-foreground">{folder ? folder.name : t('sidebar.unfiled')}</span>
          )}
          <span className="shrink-0 text-[10px] text-muted-foreground/70">{count}</span>
        </button>
        {isFolder && !isRenaming && (
          <button
            onClick={(e) => openMenu(e, 'folder', folder.id)}
            data-no-drag
            className={`shrink-0 rounded p-0.5 text-muted-foreground hover:text-foreground transition-opacity cursor-pointer ${
              menu?.kind === 'folder' && menu.id === folder.id ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
            }`}
            title={t('sidebar.folderOptions')}
          >
            <MoreHorizontal size={12} />
          </button>
        )}
      </div>
    );
  };

  const renderDateHeader = (bucket: ChatDateBucket, count: number) => (
    <div className="flex items-center justify-between gap-1 px-1" style={{ paddingLeft: 4 }}>
      <span className="truncate text-[11px] font-bold uppercase tracking-wider text-muted-foreground">{bucketLabel[bucket]}</span>
      <span className="shrink-0 text-[9px] text-muted-foreground/70">{count}</span>
    </div>
  );

  const dragging = ghost !== null;
  const hasAnything = view.pinned.length > 0 || view.groups.length > 0;
  const allSelectedPinned = selectedIds.size > 0
    && [...selectedIds].every((id) => conversations.find((c) => c.id === id)?.pinned);

  return (
    <div className="flex flex-col gap-2 pb-4">
      {/* Header + global actions */}
      <div className="flex items-center justify-between px-1">
        <span className="text-[13px] text-muted-foreground uppercase tracking-widest font-bold">
          {selecting ? t('sidebar.selectedCount', { count: selectedIds.size }) : t('sidebar.chatHistory')}
        </span>
        <div className="flex items-center gap-0.5">
          {selecting ? (
            <IconBtn title={t('sidebar.done')} onClick={exitSelection}><X size={12} /></IconBtn>
          ) : (
            <>
              {groupBy === 'folders' && <IconBtn title={t('sidebar.newFolder')} onClick={() => onCreateFolder()}><FolderPlus size={12} /></IconBtn>}
              {visibleIds.length > 0 && (
                <IconBtn title={t('sidebar.select')} onClick={() => setSelecting(true)}><ListChecks size={12} /></IconBtn>
              )}
              <IconBtn title={t('sidebar.newChat')} onClick={onNewChat}><Plus size={12} /></IconBtn>
            </>
          )}
        </div>
      </div>

      {/* Bulk actions — visible only in selection mode. */}
      {selecting && (
        <div className="mx-1 flex items-center gap-1 rounded-lg border border-border/20 bg-white/[0.03] px-1.5 py-1">
          <button
            type="button"
            onClick={selectAll}
            className="rounded-md px-1.5 py-0.5 text-[10px] text-muted-foreground hover:bg-accent/40 hover:text-foreground cursor-pointer"
          >
            {t('sidebar.selectAll')}
          </button>
          <button
            type="button"
            onClick={selectNone}
            disabled={selectedIds.size === 0}
            className="rounded-md px-1.5 py-0.5 text-[10px] text-muted-foreground hover:bg-accent/40 hover:text-foreground disabled:opacity-40 disabled:hover:bg-transparent cursor-pointer"
          >
            {t('sidebar.clearSelection')}
          </button>
          <span className="ml-auto flex items-center gap-0.5">
            <button
              type="button"
              onClick={pinSelected}
              disabled={selectedIds.size === 0}
              title={allSelectedPinned ? t('sidebar.unpin') : t('sidebar.pin')}
              aria-label={allSelectedPinned ? t('sidebar.unpin') : t('sidebar.pin')}
              className="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-40 disabled:hover:bg-transparent cursor-pointer"
            >
              {allSelectedPinned ? <PinOff size={12} /> : <Pin size={12} />}
            </button>
            <button
              type="button"
              onClick={() => void deleteSelected()}
              disabled={selectedIds.size === 0}
              title={t('sidebar.delete')}
              aria-label={t('sidebar.delete')}
              className="rounded-md p-1 text-rose-300 hover:bg-rose-500/10 disabled:opacity-40 disabled:hover:bg-transparent cursor-pointer"
            >
              <Trash2 size={12} />
            </button>
          </span>
        </div>
      )}

      {/* Search — flat (2D) glass: frost without the raised bevel/drop shadow. */}
      <div
        className="mx-1 flex items-center gap-1.5 rounded-lg glass-card-subtle border border-border/20 px-2.5 py-1"
        style={{ boxShadow: 'none' }}
      >
        <Search size={13} className="shrink-0 text-muted-foreground" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t('sidebar.searchChats')}
          className="w-full min-w-0 bg-transparent text-[12px] text-foreground placeholder:text-muted-foreground/70 outline-none"
        />
        {query && <button onClick={() => setQuery('')} className="shrink-0 text-muted-foreground hover:text-foreground cursor-pointer"><X size={12} /></button>}
      </div>

      {/* Controls: group-by (icon toggle) + optional tag filter + sort.
          Both controls are background-free so the row reads flat/2D. */}
      <div className="flex items-center gap-1 px-1">
        <div className="flex items-center gap-0.5" role="group" aria-label={t('sidebar.groupBy')}>
          <SegmentBtn active={groupBy === 'date'} title={t('sidebar.groupDate')} onClick={() => setGroupBy('date')}>
            <Clock size={12} />
          </SegmentBtn>
          <SegmentBtn active={groupBy === 'folders'} title={t('sidebar.groupFolders')} onClick={() => setGroupBy('folders')}>
            <Folder size={12} />
          </SegmentBtn>
        </div>
        <div className="ml-auto flex items-center gap-1">
          {tags.length > 0 && (
            <HistorySelect
              value={tagFilter || ALL_TAGS}
              options={tagOptions}
              onChange={(v) => setTagFilter(v === ALL_TAGS ? '' : v)}
              title={t('sidebar.filterTag')}
              className="max-w-[76px]"
            />
          )}
          <HistorySelect
            value={sort}
            options={sortOptions}
            onChange={setSort}
            title={t('sidebar.sortBy')}
          />
        </div>
      </div>

      {/* List */}
      <div className={`flex flex-col gap-2.5 max-h-[45vh] overflow-y-auto pr-1 ${dragging ? 'cursor-grabbing' : ''}`}>
        {view.pinned.length > 0 && (
          <div data-droppable data-drop-key="pinned" className={`flex flex-col gap-1.5 rounded-lg ${dropKey === 'pinned' && dragging ? 'bg-primary/10 ring-1 ring-primary/40' : ''}`}>
            <div className="flex items-center gap-1.5 px-1">
              <Pin size={11} className="text-amber-400" weight="fill" />
              <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">{t('sidebar.pinned')}</span>
            </div>
            {view.pinned.map((c) => renderRow(c))}
          </div>
        )}

        {view.groups.map((g) => {
          if (g.bucket) {
            return (
              <div key={`bucket:${g.bucket}`} className="flex flex-col gap-1.5 rounded-lg">
                {renderDateHeader(g.bucket, g.conversations.length)}
                {g.conversations.map((c) => renderRow(c))}
              </div>
            );
          }
          const key = g.folder ? `folder:${g.folder.id}` : 'unfiled';
          const isDropTarget = dropKey === key && dragging;
          return (
            <div
              key={key}
              data-droppable
              data-drop-key={key}
              className={`flex flex-col gap-1.5 rounded-lg transition-colors ${isDropTarget ? 'bg-primary/10 ring-1 ring-primary/40' : ''}`}
            >
              {(g.folder || !query.trim()) && renderGroupHeader(g.folder, g.conversations.length, g.depth)}
              {!(g.folder?.collapsed) && g.conversations.map((c) => renderRow(c, g.depth + (g.folder ? 1 : 0)))}
            </div>
          );
        })}

        {!hasAnything && (
          <span className="text-[11px] text-muted-foreground italic text-center py-2">
            {query.trim() ? t('sidebar.noMatches') : t('sidebar.noSessions')}
          </span>
        )}
      </div>

      {/* Drag ghost */}
      {ghost && (
        <div className="pointer-events-none fixed z-[110] max-w-[180px] truncate rounded-lg glass-card-strong border border-border/40 px-2 py-1 text-[11px] text-foreground shadow-xl" style={{ left: ghost.x + 12, top: ghost.y + 12 }}>
          {ghost.label}
        </div>
      )}

      {/* Options menu */}
      {menu && (
        <ChatHistoryMenu
          anchor={menu}
          conversation={menu.kind === 'chat' ? conversations.find((c) => c.id === menu.id) : undefined}
          folder={menu.kind === 'folder' ? folders.find((f) => f.id === menu.id) : undefined}
          folders={folders}
          onClose={() => setMenu(null)}
          onRename={(kind, id) => setRenaming({ kind, id })}
          onSetConversationColor={onSetConversationColor}
          onSetFolderColor={onSetFolderColor}
          onMoveConversation={onMoveConversation}
          onTogglePin={onTogglePin}
          onForkConversation={onForkConversation}
          onPurge={async (id) => { if (await confirmDialog({ title: t('sidebar.confirmDeleteForever'), tone: 'danger' })) onDeleteConversation(id); }}
          onDeleteFolder={onDeleteFolder}
          onMoveFolder={onMoveFolder}
          onAddTag={onAddTag}
          onRemoveTag={onRemoveTag}
        />
      )}
    </div>
  );
}

function IconBtn({ children, title, onClick, active }: { children: React.ReactNode; title: string; onClick: () => void; active?: boolean }) {
  return (
    <button
      onClick={onClick}
      title={title}
      className={`p-1 rounded-md flex items-center cursor-pointer transition-all border border-border/5 ${
        active ? 'bg-white/[0.08] text-foreground' : 'text-muted-foreground hover:bg-accent hover:text-foreground'
      }`}
    >
      {children}
    </button>
  );
}

/** One option of the icon-only segment toggle (group by date / folders). */
function SegmentBtn({ active, title, onClick, children }: { active: boolean; title: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      aria-label={title}
      aria-pressed={active}
      className={cn(
        'flex h-6 w-6 items-center justify-center rounded-md cursor-pointer transition-colors',
        active ? 'text-foreground' : 'text-muted-foreground/60 hover:text-foreground',
      )}
    >
      {children}
    </button>
  );
}

/** A compact themed select built on the shared frosted `Select` — a native
 *  <select> popup is OS-rendered and cannot adopt the glass design language. */
function HistorySelect<T extends string>({
  value,
  options,
  onChange,
  title,
  className,
  align = 'end',
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
  title: string;
  className?: string;
  align?: 'start' | 'center' | 'end';
}) {
  return (
    <Select value={value} onValueChange={(v) => v != null && onChange(v as T)}>
      <SelectTrigger
        size="sm"
        title={title}
        className={cn(
          'history-select border-border/20 bg-transparent text-[11px] text-muted-foreground hover:bg-transparent hover:text-foreground dark:bg-transparent dark:hover:bg-transparent outline-none focus-visible:border-border/40 focus-visible:ring-0',
          className,
        )}
      >
        <SelectValue />
      </SelectTrigger>
      <SelectContent align={align} side="bottom" alignItemWithTrigger={false} className="w-44 min-w-[176px]">
        {options.map((o) => (
          <SelectItem key={o.value} value={o.value} className="text-[12px]">
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

"use client";

import React, { useMemo, useState } from 'react';
import {
  Check,
  ChevronDown,
  Folder,
  FolderOpen,
  FolderPlus,
  MoreHorizontal,
  Pencil,
  Pin,
  PinOff,
  Plus,
  Search,
  Trash2,
  X,
} from '@/lib/icons';
import { useT } from '@/lib/i18n';
import {
  buildChatHistoryView,
  CHAT_COLORS,
  type ChatFolder,
  type ChatOrganizationApi,
  type ChatSortMode,
  type Conversation,
} from '@/lib/chat/chat-organization';

export interface ChatHistoryPanelProps {
  conversations: Conversation[];
  organization: ChatOrganizationApi;
  activeConversationId: string | null;
  onSelectConversation: (id: string) => void;
  onNewChat: () => void;
  onDeleteConversation: (id: string) => void;
}

type MenuTarget = { kind: 'chat' | 'folder'; id: string } | null;
type RenameTarget = { kind: 'chat' | 'folder'; id: string } | null;

/** Compact color swatch strip. `value === null` renders a "no color" reset. */
function ColorSwatches({ value, onPick }: { value: string | null; onPick: (color: string | null) => void }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {CHAT_COLORS.map((c) => (
        <button
          key={c.id}
          onClick={() => onPick(c.value)}
          className="flex h-4 w-4 items-center justify-center rounded-full border border-black/20 transition-transform hover:scale-110 cursor-pointer"
          style={{ background: c.value }}
          title={c.id}
        >
          {value === c.value && <Check size={9} className="text-white" />}
        </button>
      ))}
      <button
        onClick={() => onPick(null)}
        className="flex h-4 w-4 items-center justify-center rounded-full border border-border/60 text-muted-foreground hover:text-foreground cursor-pointer"
        title="none"
      >
        <X size={9} />
      </button>
    </div>
  );
}

export function ChatHistoryPanel({
  conversations,
  organization,
  activeConversationId,
  onSelectConversation,
  onNewChat,
  onDeleteConversation,
}: ChatHistoryPanelProps) {
  const t = useT();
  const {
    folders,
    createFolder: onCreateFolder,
    renameFolder: onRenameFolder,
    deleteFolder: onDeleteFolder,
    toggleFolder: onToggleFolder,
    setFolderColor: onSetFolderColor,
    moveConversation: onMoveConversation,
    setConversationColor: onSetConversationColor,
    togglePin: onTogglePin,
    renameConversation: onRenameConversation,
  } = organization;
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState<ChatSortMode>('recent');
  const [menu, setMenu] = useState<MenuTarget>(null);
  const [renaming, setRenaming] = useState<RenameTarget>(null);

  const view = useMemo(
    () => buildChatHistoryView(conversations, folders, { query, sort }),
    [conversations, folders, query, sort],
  );

  const commitRename = (target: RenameTarget, value: string) => {
    if (target) {
      const trimmed = value.trim();
      if (trimmed) {
        if (target.kind === 'chat') onRenameConversation(target.id, trimmed);
        else onRenameFolder(target.id, trimmed);
      }
    }
    setRenaming(null);
  };

  const renameInput = (target: RenameTarget, initial: string) => (
    <input
      autoFocus
      defaultValue={initial}
      onClick={(e) => e.stopPropagation()}
      onBlur={(e) => commitRename(target, e.target.value)}
      onKeyDown={(e) => {
        if (e.key === 'Enter') commitRename(target, (e.target as HTMLInputElement).value);
        if (e.key === 'Escape') setRenaming(null);
      }}
      className="w-full min-w-0 rounded-md border border-border/50 bg-background/60 px-1.5 py-0.5 text-[11px] text-foreground outline-none focus:border-border"
    />
  );

  const renderChatRow = (c: Conversation) => {
    const isActive = activeConversationId === c.id;
    const isRenaming = renaming?.kind === 'chat' && renaming.id === c.id;
    return (
      <div key={c.id} className="relative">
        <div
          onClick={() => !isRenaming && onSelectConversation(c.id)}
          className={`flex items-center justify-between gap-1 rounded-xl px-2.5 py-1.5 text-[11px] cursor-pointer group transition-all border border-transparent ${
            isActive
              ? 'bg-white/[0.04] border-border/20 text-foreground font-semibold'
              : 'bg-transparent text-muted-foreground hover:bg-accent/25 hover:text-foreground'
          }`}
        >
          <span className="flex items-center gap-1.5 min-w-0 flex-1">
            {c.pinned && <Pin size={10} className="shrink-0 text-amber-400" weight="fill" />}
            {c.color && <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: c.color }} />}
            {isRenaming ? (
              renameInput(renaming, c.title)
            ) : (
              <span className="truncate">{c.title || t('sidebar.untitledSession')}</span>
            )}
          </span>
          {!isRenaming && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                setMenu(menu?.kind === 'chat' && menu.id === c.id ? null : { kind: 'chat', id: c.id });
              }}
              className={`shrink-0 rounded p-0.5 hover:text-foreground transition-opacity ${
                menu?.kind === 'chat' && menu.id === c.id ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
              }`}
              title={t('sidebar.chatOptions')}
            >
              <MoreHorizontal size={13} />
            </button>
          )}
        </div>

        {menu?.kind === 'chat' && menu.id === c.id && (
          <div className="absolute right-0 z-30 mt-1 w-44 rounded-xl glass-card-strong border border-border/40 p-2 flex flex-col gap-2 shadow-xl">
            <div className="flex flex-col gap-1">
              <span className="text-[9px] uppercase tracking-widest font-bold text-muted-foreground">{t('sidebar.color')}</span>
              <ColorSwatches value={c.color ?? null} onPick={(color) => { onSetConversationColor(c.id, color); setMenu(null); }} />
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-[9px] uppercase tracking-widest font-bold text-muted-foreground">{t('sidebar.moveTo')}</span>
              <div className="flex flex-wrap gap-1">
                <button onClick={() => { onMoveConversation(c.id, null); setMenu(null); }} className="rounded-md bg-accent/40 px-1.5 py-0.5 text-[10px] hover:bg-accent cursor-pointer">
                  {t('sidebar.unfiled')}
                </button>
                {folders.map((f) => (
                  <button key={f.id} onClick={() => { onMoveConversation(c.id, f.id); setMenu(null); }} className="flex items-center gap-1 rounded-md bg-accent/40 px-1.5 py-0.5 text-[10px] hover:bg-accent cursor-pointer">
                    <span className="h-1.5 w-1.5 rounded-full" style={{ background: f.color }} />
                    <span className="max-w-[80px] truncate">{f.name}</span>
                  </button>
                ))}
              </div>
            </div>
            <div className="flex flex-col gap-0.5 border-t border-border/20 pt-1.5">
              <button onClick={() => { setRenaming({ kind: 'chat', id: c.id }); setMenu(null); }} className="flex items-center gap-2 rounded-md px-1.5 py-1 text-[10px] hover:bg-accent/40 cursor-pointer">
                <Pencil size={11} /> {t('sidebar.rename')}
              </button>
              <button onClick={() => { onTogglePin(c.id); setMenu(null); }} className="flex items-center gap-2 rounded-md px-1.5 py-1 text-[10px] hover:bg-accent/40 cursor-pointer">
                {c.pinned ? <PinOff size={11} /> : <Pin size={11} />} {c.pinned ? t('sidebar.unpin') : t('sidebar.pin')}
              </button>
              <button onClick={() => { onDeleteConversation(c.id); setMenu(null); }} className="flex items-center gap-2 rounded-md px-1.5 py-1 text-[10px] text-rose-400 hover:bg-rose-500/10 cursor-pointer">
                <Trash2 size={11} /> {t('sidebar.delete')}
              </button>
            </div>
          </div>
        )}
      </div>
    );
  };

  const renderGroupHeader = (folder: ChatFolder | null, count: number) => {
    const isFolder = folder !== null;
    const isRenaming = isFolder && renaming?.kind === 'folder' && renaming.id === folder.id;
    const collapsed = isFolder && folder.collapsed;
    return (
      <div className="relative flex items-center justify-between gap-1 px-1 group">
        <button
          onClick={() => isFolder && onToggleFolder(folder.id)}
          className="flex items-center gap-1.5 min-w-0 flex-1 text-left cursor-pointer"
        >
          {isFolder && <ChevronDown size={11} className={`shrink-0 text-muted-foreground transition-transform ${collapsed ? '-rotate-90' : ''}`} />}
          {isFolder ? (
            collapsed ? <Folder size={12} className="shrink-0" style={{ color: folder.color }} />
              : <FolderOpen size={12} className="shrink-0" style={{ color: folder.color }} />
          ) : (
            <Folder size={12} className="shrink-0 text-muted-foreground" />
          )}
          {isRenaming ? (
            renameInput(renaming, folder.name)
          ) : (
            <span className="truncate text-[10px] font-bold uppercase tracking-wider text-muted-foreground">{folder ? folder.name : t('sidebar.unfiled')}</span>
          )}
          <span className="shrink-0 text-[9px] text-muted-foreground/70">{count}</span>
        </button>
        {isFolder && !isRenaming && (
          <button
            onClick={() => setMenu(menu?.kind === 'folder' && menu.id === folder.id ? null : { kind: 'folder', id: folder.id })}
            className={`shrink-0 rounded p-0.5 text-muted-foreground hover:text-foreground transition-opacity cursor-pointer ${
              menu?.kind === 'folder' && menu.id === folder.id ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
            }`}
            title={t('sidebar.folderOptions')}
          >
            <MoreHorizontal size={12} />
          </button>
        )}
        {menu?.kind === 'folder' && folder && menu.id === folder.id && (
          <div className="absolute right-0 top-5 z-30 w-40 rounded-xl glass-card-strong border border-border/40 p-2 flex flex-col gap-2 shadow-xl">
            <div className="flex flex-col gap-1">
              <span className="text-[9px] uppercase tracking-widest font-bold text-muted-foreground">{t('sidebar.color')}</span>
              <ColorSwatches value={folder.color} onPick={(color) => { if (color) onSetFolderColor(folder.id, color); }} />
            </div>
            <div className="flex flex-col gap-0.5 border-t border-border/20 pt-1.5">
              <button onClick={() => { setRenaming({ kind: 'folder', id: folder.id }); setMenu(null); }} className="flex items-center gap-2 rounded-md px-1.5 py-1 text-[10px] hover:bg-accent/40 cursor-pointer">
                <Pencil size={11} /> {t('sidebar.rename')}
              </button>
              <button onClick={() => { onDeleteFolder(folder.id); setMenu(null); }} className="flex items-center gap-2 rounded-md px-1.5 py-1 text-[10px] text-rose-400 hover:bg-rose-500/10 cursor-pointer">
                <Trash2 size={11} /> {t('sidebar.delete')}
              </button>
            </div>
          </div>
        )}
      </div>
    );
  };

  const searching = query.trim().length > 0;
  const hasAnything = view.pinned.length > 0 || view.groups.length > 0;

  return (
    <div className="flex flex-col gap-2.5 pb-4">
      {/* Click-away scrim: closes an open row/folder menu. Sits under the menus
          (z-20) but over the rest of the panel so a click elsewhere — including
          another row — dismisses the menu first. */}
      {menu && <div className="fixed inset-0 z-20" onClick={() => setMenu(null)} />}
      {/* Header: title + new chat + new folder */}
      <div className="flex items-center justify-between px-1">
        <span className="text-[9px] text-muted-foreground uppercase tracking-widest font-bold">{t('sidebar.chatHistory')}</span>
        <div className="flex items-center gap-0.5">
          <button
            onClick={onCreateFolder}
            className="p-1 rounded-md text-muted-foreground hover:bg-accent hover:text-foreground flex items-center cursor-pointer transition-all border border-border/5"
            title={t('sidebar.newFolder')}
          >
            <FolderPlus size={12} />
          </button>
          <button
            onClick={onNewChat}
            className="p-1 rounded-md text-muted-foreground hover:bg-accent hover:text-foreground flex items-center cursor-pointer transition-all border border-border/5"
            title={t('sidebar.newChat')}
          >
            <Plus size={12} />
          </button>
        </div>
      </div>

      {/* Search + sort */}
      <div className="flex items-center gap-1 px-1">
        <div className="flex flex-1 items-center gap-1.5 rounded-lg glass-card-subtle border border-border/20 px-2 py-1">
          <Search size={11} className="shrink-0 text-muted-foreground" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('sidebar.searchChats')}
            className="w-full min-w-0 bg-transparent text-[11px] text-foreground placeholder:text-muted-foreground/70 outline-none"
          />
          {query && (
            <button onClick={() => setQuery('')} className="shrink-0 text-muted-foreground hover:text-foreground cursor-pointer">
              <X size={11} />
            </button>
          )}
        </div>
        <div className="relative flex items-center">
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as ChatSortMode)}
            className="appearance-none rounded-lg glass-card-subtle border border-border/20 py-1 pl-1.5 pr-4 text-[10px] text-muted-foreground outline-none cursor-pointer"
            title={t('sidebar.sortBy')}
          >
            <option value="recent">{t('sidebar.sortRecent')}</option>
            <option value="created">{t('sidebar.sortCreated')}</option>
            <option value="alpha">{t('sidebar.sortAlpha')}</option>
          </select>
          <ChevronDown size={10} className="pointer-events-none absolute right-1 text-muted-foreground" />
        </div>
      </div>

      {/* List — no inner scroll: the sidebar's own scroll region owns overflow,
          so popover menus are never clipped by this container. */}
      <div className="flex flex-col gap-2.5">
        {view.pinned.length > 0 && (
          <div className="flex flex-col gap-0.5">
            <div className="flex items-center gap-1.5 px-1">
              <Pin size={11} className="text-amber-400" weight="fill" />
              <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">{t('sidebar.pinned')}</span>
            </div>
            {view.pinned.map(renderChatRow)}
          </div>
        )}

        {view.groups.map((g) => (
          <div key={g.folder?.id ?? '__unfiled__'} className="flex flex-col gap-0.5">
            {renderGroupHeader(g.folder, g.conversations.length)}
            {!(g.folder?.collapsed) && g.conversations.map(renderChatRow)}
          </div>
        ))}

        {!hasAnything && (
          <span className="text-[10px] text-muted-foreground italic text-center py-2">
            {searching ? t('sidebar.noMatches') : t('sidebar.noSessions')}
          </span>
        )}
      </div>
    </div>
  );
}

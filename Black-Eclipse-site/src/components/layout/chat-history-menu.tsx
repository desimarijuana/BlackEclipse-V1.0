"use client";

import React, { useState } from 'react';
import { createPortal } from 'react-dom';
import { Check, Folder, Pencil, Pin, PinOff, Plus, Trash2, X } from '@/lib/icons';
import { useT } from '@/lib/i18n';
import {
  CHAT_COLORS,
  folderSubtreeIds,
  type ChatFolder,
  type Conversation,
} from '@/lib/chat/chat-organization';

/** The target and viewport anchor of an open options menu. */
export interface MenuAnchor {
  kind: 'chat' | 'folder';
  id: string;
  x: number;
  y: number;
  up: boolean;
}

export interface ChatHistoryMenuProps {
  anchor: MenuAnchor;
  conversation?: Conversation;
  folder?: ChatFolder;
  folders: ChatFolder[];
  onClose: () => void;
  onRename: (kind: 'chat' | 'folder', id: string) => void;
  onSetConversationColor: (id: string, color: string | null) => void;
  onSetFolderColor: (id: string, color: string) => void;
  onMoveConversation: (id: string, folderId: string | null) => void;
  onTogglePin: (id: string) => void;
  onPurge: (id: string) => void;
  onDeleteFolder: (id: string) => void;
  onMoveFolder: (id: string, parentId: string | null, beforeId: string | null) => void;
  onAddTag: (id: string, tag: string) => void;
  onRemoveTag: (id: string, tag: string) => void;
}

/** Compact color swatch strip. The trailing X clears the color. */
export function ColorSwatches({ value, onPick }: { value: string | null; onPick: (color: string | null) => void }) {
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

const chip = 'rounded-md bg-accent/40 px-1.5 py-0.5 text-[10px] hover:bg-accent cursor-pointer';
const action = 'flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-[11px] cursor-pointer transition-colors';

function TagEditor({ conv, onAdd, onRemove, onClose }: {
  conv: Conversation;
  onAdd: (id: string, tag: string) => void;
  onRemove: (id: string, tag: string) => void;
  onClose: () => void;
}) {
  const t = useT();
  const [value, setValue] = useState('');
  const tags = conv.tags ?? [];
  const commit = () => {
    if (value.trim()) onAdd(conv.id, value);
    setValue('');
  };
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-[9px] uppercase tracking-widest font-bold text-muted-foreground">{t('sidebar.tags')}</span>
      {tags.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {tags.map((tag) => (
            <span key={tag} className="flex items-center gap-1 rounded-md bg-white/[0.06] px-1.5 py-0.5 text-[10px] text-foreground">
              {tag}
              <button onClick={() => onRemove(conv.id, tag)} className="text-muted-foreground hover:text-rose-400 cursor-pointer"><X size={9} /></button>
            </span>
          ))}
        </div>
      )}
      <div className="flex items-center gap-1 rounded-md border border-border/40 px-1.5 py-0.5">
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') commit(); if (e.key === 'Escape') onClose(); }}
          placeholder={t('sidebar.addTag')}
          className="w-full min-w-0 bg-transparent text-[10px] text-foreground placeholder:text-muted-foreground/70 outline-none"
        />
        <button onClick={commit} className="text-muted-foreground hover:text-foreground cursor-pointer"><Plus size={11} /></button>
      </div>
    </div>
  );
}

/** The portal-rendered options menu for a chat or folder. */
export function ChatHistoryMenu(props: ChatHistoryMenuProps) {
  const {
    anchor, conversation: chat, folder, folders, onClose,
    onRename, onSetConversationColor, onSetFolderColor, onMoveConversation, onTogglePin,
    onPurge, onDeleteFolder, onMoveFolder, onAddTag, onRemoveTag,
  } = props;
  const t = useT();
  if (typeof document === 'undefined') return null;

  // Folders a chat can move to, and parents a folder can move under (its own
  // subtree is excluded so a folder can never be nested inside itself).
  const banned = folder ? new Set(folderSubtreeIds(folders, folder.id)) : new Set<string>();

  const body = chat ? (
    <div className="flex max-h-[70vh] flex-col gap-2 overflow-y-auto p-2">
      <ColorSwatches value={chat.color ?? null} onPick={(color) => { onSetConversationColor(chat.id, color); }} />
      <TagEditor conv={chat} onAdd={onAddTag} onRemove={onRemoveTag} onClose={onClose} />
      <div className="flex flex-col gap-1">
        <span className="text-[9px] uppercase tracking-widest font-bold text-muted-foreground">{t('sidebar.moveTo')}</span>
        <div className="flex flex-wrap gap-1">
          <button onClick={() => { onMoveConversation(chat.id, null); onClose(); }} className={chip}>{t('sidebar.unfiled')}</button>
          {folders.map((f) => (
            <button key={f.id} onClick={() => { onMoveConversation(chat.id, f.id); onClose(); }} className={`flex items-center gap-1 ${chip}`}>
              <span className="h-1.5 w-1.5 rounded-full" style={{ background: f.color }} />
              <span className="max-w-[90px] truncate">{f.name}</span>
            </button>
          ))}
        </div>
      </div>
      <div className="flex flex-col gap-0.5 border-t border-border/20 pt-1.5">
        <button onClick={() => { onRename('chat', chat.id); onClose(); }} className={`${action} hover:bg-accent/40`}><Pencil size={12} /> {t('sidebar.rename')}</button>
        <button onClick={() => { onTogglePin(chat.id); onClose(); }} className={`${action} hover:bg-accent/40`}>
          {chat.pinned ? <PinOff size={12} /> : <Pin size={12} />} {chat.pinned ? t('sidebar.unpin') : t('sidebar.pin')}
        </button>
        <button onClick={() => { onPurge(chat.id); onClose(); }} className={`${action} text-rose-400 hover:bg-rose-500/10`}><Trash2 size={12} /> {t('sidebar.delete')}</button>
      </div>
    </div>
  ) : folder ? (
    <>
      <div className="flex items-center gap-2 border-b border-border/20 px-3 py-2.5">
        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg" style={{ background: `${folder.color}22` }}>
          <Folder size={13} style={{ color: folder.color }} />
        </span>
        <span className="min-w-0 flex-1 truncate text-[11px] font-semibold text-foreground">{folder.name}</span>
      </div>
      <div className="flex flex-col gap-2 px-3 py-2.5">
        <span className="text-[9px] uppercase tracking-widest font-bold text-muted-foreground">{t('sidebar.color')}</span>
        <ColorSwatches value={folder.color} onPick={(color) => { if (color) onSetFolderColor(folder.id, color); }} />
      </div>
      <div className="flex flex-col gap-1 px-3 pb-2.5">
        <span className="text-[9px] uppercase tracking-widest font-bold text-muted-foreground">{t('sidebar.moveTo')}</span>
        <div className="flex flex-wrap gap-1">
          <button onClick={() => { onMoveFolder(folder.id, null, null); onClose(); }} className={chip}>{t('sidebar.moveToRoot')}</button>
          {folders.filter((f) => !banned.has(f.id)).map((f) => (
            <button key={f.id} onClick={() => { onMoveFolder(folder.id, f.id, null); onClose(); }} className={`flex items-center gap-1 ${chip}`}>
              <span className="h-1.5 w-1.5 rounded-full" style={{ background: f.color }} />
              <span className="max-w-[80px] truncate">{f.name}</span>
            </button>
          ))}
        </div>
      </div>
      <div className="flex flex-col gap-0.5 border-t border-border/20 p-1.5">
        <button onClick={() => { onRename('folder', folder.id); onClose(); }} className={`${action} text-foreground hover:bg-accent/40`}><Pencil size={12} /> {t('sidebar.rename')}</button>
        <button onClick={() => { onDeleteFolder(folder.id); onClose(); }} className={`${action} text-rose-400 hover:bg-rose-500/10`}><Trash2 size={12} /> {t('sidebar.deleteFolder')}</button>
      </div>
    </>
  ) : null;

  return createPortal(
    <>
      <div className="fixed inset-0 z-[90]" onClick={onClose} />
      <div
        className="fixed z-[100] w-52 overflow-hidden rounded-xl glass-card-strong border border-border/40 shadow-xl"
        style={{
          left: Math.max(8, anchor.x - 208),
          top: anchor.up ? undefined : anchor.y + 4,
          bottom: anchor.up ? window.innerHeight - anchor.y + 4 : undefined,
        }}
      >
        {body}
      </div>
    </>,
    document.body,
  );
}

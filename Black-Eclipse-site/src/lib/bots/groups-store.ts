// ── Bot group chat store ──────────────────────────────────────────────────────
// Group rooms that gather 2–6 of the user's bots into one conversation. This is
// presentation-layer state (which bots share a room and what was said), so it
// follows the repo's client-side persistence convention — the same approach as
// `lib/bots/chat-store.ts`. Replies still come from the real harness; nothing
// here fabricates a bot turn.

'use client';

import { useEffect } from 'react';
import { create } from 'zustand';

export const BOT_GROUPS_KEY = 'be_bot_groups_v1';

export interface BotGroup {
  id: string;
  name: string;
  /** Member bot ids (2–6). */
  memberIds: string[];
  /** Optional uploaded group photo (data URL). */
  image?: string;
  createdAt: string;
}

export interface GroupMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  at: string;
  /** For assistant turns: the bot id that spoke; absent means the room itself. */
  authorId?: string;
  /** Display name shown on the bubble. */
  authorName?: string;
  error?: boolean;
  /** Optional thumbs feedback on an assistant turn. */
  feedback?: 'up' | 'down';
  /** Parallel fan-outs this member ran, for the live agent card. */
  delegations?: import('@/lib/agent/response-model').DelegationView[];
}

interface Persisted {
  groups: BotGroup[];
  byGroup: Record<string, GroupMessage[]>;
}

interface BotGroupsStore {
  groups: BotGroup[];
  byGroup: Record<string, GroupMessage[]>;
  hydrated: boolean;
  hydrate: () => void;
  createGroup: (input: { name: string; memberIds: string[]; image?: string }) => BotGroup;
  renameGroup: (id: string, name: string) => void;
  setGroupImage: (id: string, dataUrl: string | null) => void;
  /** Replace the member set (clamped to 2–6). */
  setMembers: (id: string, memberIds: string[]) => void;
  deleteGroup: (id: string) => void;
  appendMessage: (groupId: string, message: GroupMessage) => void;
  /** Replace a room's whole message list (used to truncate on edit/regenerate). */
  setMessages: (groupId: string, messages: GroupMessage[]) => void;
  /** Patch one message in place — used to fill the live streaming reply. */
  updateMessage: (groupId: string, id: string, patch: Partial<GroupMessage>) => void;
  clearMessages: (groupId: string) => void;
}

function persist(groups: BotGroup[], byGroup: Record<string, GroupMessage[]>) {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(BOT_GROUPS_KEY, JSON.stringify({ groups, byGroup } satisfies Persisted));
  } catch {
    /* quota / private mode — in-memory only */
  }
}

function isGroup(v: unknown): v is BotGroup {
  if (!v || typeof v !== 'object') return false;
  const g = v as Record<string, unknown>;
  return (
    typeof g.id === 'string' &&
    typeof g.name === 'string' &&
    Array.isArray(g.memberIds) &&
    g.memberIds.every((m) => typeof m === 'string')
  );
}

function isMessage(v: unknown): v is GroupMessage {
  if (!v || typeof v !== 'object') return false;
  const m = v as Record<string, unknown>;
  return (
    typeof m.id === 'string' &&
    (m.role === 'user' || m.role === 'assistant') &&
    typeof m.content === 'string'
  );
}

function newGroupId(): string {
  return `grp_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
}

export const useBotGroupsStore = create<BotGroupsStore>((set, get) => {
  const commit = (groups: BotGroup[], byGroup: Record<string, GroupMessage[]>) => {
    persist(groups, byGroup);
    set({ groups, byGroup });
  };

  return {
    groups: [],
    byGroup: {},
    hydrated: false,

    hydrate: () => {
      let groups: BotGroup[] = [];
      let byGroup: Record<string, GroupMessage[]> = {};
      if (typeof window !== 'undefined') {
        try {
          const raw = localStorage.getItem(BOT_GROUPS_KEY);
          if (raw) {
            const parsed = JSON.parse(raw) as Partial<Persisted>;
            if (Array.isArray(parsed.groups)) groups = parsed.groups.filter(isGroup);
            if (parsed.byGroup && typeof parsed.byGroup === 'object') {
              for (const [id, list] of Object.entries(parsed.byGroup)) {
                if (Array.isArray(list)) byGroup[id] = list.filter(isMessage);
              }
            }
          }
        } catch {
          groups = [];
          byGroup = {};
        }
      }
      set({ groups, byGroup, hydrated: true });
    },

    createGroup: ({ name, memberIds, image }) => {
      const group: BotGroup = {
        id: newGroupId(),
        name: name.trim(),
        memberIds: [...memberIds],
        image,
        createdAt: new Date().toISOString(),
      };
      commit([group, ...get().groups], get().byGroup);
      return group;
    },

    renameGroup: (id, name) => {
      commit(get().groups.map((g) => (g.id === id ? { ...g, name: name.trim() || g.name } : g)), get().byGroup);
    },

    setGroupImage: (id, dataUrl) => {
      commit(
        get().groups.map((g) => {
          if (g.id !== id) return g;
          const next = { ...g };
          if (dataUrl) next.image = dataUrl;
          else delete next.image;
          return next;
        }),
        get().byGroup,
      );
    },

    setMembers: (id, memberIds) => {
      const unique = [...new Set(memberIds)].slice(0, 6);
      if (unique.length < 2) return;
      commit(get().groups.map((g) => (g.id === id ? { ...g, memberIds: unique } : g)), get().byGroup);
    },

    deleteGroup: (id) => {
      const byGroup = { ...get().byGroup };
      delete byGroup[id];
      commit(get().groups.filter((g) => g.id !== id), byGroup);
    },

    appendMessage: (groupId, message) => {
      const byGroup = { ...get().byGroup, [groupId]: [...(get().byGroup[groupId] ?? []), message] };
      commit(get().groups, byGroup);
    },

    setMessages: (groupId, messages) => {
      commit(get().groups, { ...get().byGroup, [groupId]: messages });
    },

    updateMessage: (groupId, id, patch) => {
      const list = get().byGroup[groupId];
      if (!list) return;
      const byGroup = {
        ...get().byGroup,
        [groupId]: list.map((m) => (m.id === id ? { ...m, ...patch } : m)),
      };
      commit(get().groups, byGroup);
    },

    clearMessages: (groupId) => {
      const byGroup = { ...get().byGroup };
      delete byGroup[groupId];
      commit(get().groups, byGroup);
    },
  };
});

export function useHydrateBotGroups() {
  const hydrate = useBotGroupsStore((s) => s.hydrate);
  const hydrated = useBotGroupsStore((s) => s.hydrated);
  useEffect(() => {
    if (!hydrated) hydrate();
  }, [hydrated, hydrate]);
}

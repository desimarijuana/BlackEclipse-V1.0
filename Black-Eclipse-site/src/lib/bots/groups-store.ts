// ── Bot group chat store ──────────────────────────────────────────────────────
// Group rooms that gather 2–6 of the user's bots into one conversation. The
// store hydrates from localStorage for an instant UI, then mirrors the document
// to the server (`BotState`, key `groups`) so cleared browser storage or a
// second tab recovers the rooms. Local state always remains the source of truth
// while offline; the newest client timestamp wins. Replies still come from the
// real harness — nothing here fabricates a bot turn.

'use client';

import { useEffect } from 'react';
import { create } from 'zustand';
import {
  newBotStateEnvelope,
  pullBotState,
  queueBotStatePush,
  readLocalEnvelope,
  shouldAdoptRemote,
  shouldPushLocal,
  writeLocalEnvelope,
  type BotStateEnvelope,
} from '@/lib/bots/state-sync';

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
  /** A blocking permission decision raised by this member's turn. */
  pendingApproval?: import('@/lib/agent/response-model').PendingApproval;
  /** A paused `clarify` question from this member's turn. */
  pendingClarification?: import('@/lib/agent/response-model').PendingClarification;
  /** True when this turn came from an autonomous run (schedule / Run now). */
  scheduled?: boolean;
  /** Execution id of the autonomous run — the idempotency key. */
  runId?: string;
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
  /** Remove a deleted bot from every room (and drop rooms left with no members). */
  removeMember: (botId: string) => void;
  deleteGroup: (id: string) => void;
  appendMessage: (groupId: string, message: GroupMessage) => void;
  /** Append an autonomous run's answer once (deduped by execution id). */
  appendScheduled: (groupId: string, message: GroupMessage & { runId: string }) => boolean;
  /** Replace a room's whole message list (used to truncate on edit/regenerate). */
  setMessages: (groupId: string, messages: GroupMessage[]) => void;
  /** Patch one message in place — used to fill the live streaming reply. A
   *  streaming caller passes `persist=false`; the terminal patch persists. */
  updateMessage: (groupId: string, id: string, patch: Partial<GroupMessage>, persist?: boolean) => void;
  clearMessages: (groupId: string) => void;
}

/** Validate a decoded document from either storage medium. */
function sanitizePersisted(input: unknown): Persisted {
  const parsed = (input ?? {}) as Partial<Persisted>;
  const groups = Array.isArray(parsed.groups) ? parsed.groups.filter(isGroup) : [];
  const byGroup: Record<string, GroupMessage[]> = {};
  if (parsed.byGroup && typeof parsed.byGroup === 'object') {
    for (const [id, list] of Object.entries(parsed.byGroup)) {
      if (Array.isArray(list)) byGroup[id] = list.filter(isMessage);
    }
  }
  return { groups, byGroup };
}

/** Persist locally and queue the server mirror (best effort). */
function persist(
  groups: BotGroup[],
  byGroup: Record<string, GroupMessage[]>,
  envelope?: BotStateEnvelope<Persisted>,
) {
  const next = envelope ?? newBotStateEnvelope({ groups, byGroup });
  writeLocalEnvelope(BOT_GROUPS_KEY, next);
  queueBotStatePush('groups', next);
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
  const commit = (groups: BotGroup[], byGroup: Record<string, GroupMessage[]>, persistNow = true) => {
    if (persistNow) persist(groups, byGroup);
    set({ groups, byGroup });
  };

  /** Reconcile with the durable mirror without ever blocking the local render.
   *  The remote copy is adopted only when its client timestamp is newer; a
   *  newer local copy is pushed instead. */
  const syncFromServer = async () => {
    const remote = await pullBotState('groups');
    const local = readLocalEnvelope<Persisted>(BOT_GROUPS_KEY);
    if (!remote) {
      // First run after the upgrade: seed the mirror with local rooms.
      if (local) queueBotStatePush('groups', local);
      return;
    }
    if (shouldAdoptRemote(local?.updatedAt, remote.updatedAt)) {
      try {
        const data = sanitizePersisted(JSON.parse(remote.document) as unknown);
        const envelope = newBotStateEnvelope(data, new Date(remote.updatedAt));
        writeLocalEnvelope(BOT_GROUPS_KEY, envelope);
        set({ groups: data.groups, byGroup: data.byGroup });
      } catch {
        /* malformed mirror — keep the local copy */
      }
      return;
    }
    if (local && shouldPushLocal(local.updatedAt, remote.updatedAt)) {
      queueBotStatePush('groups', local);
    }
  };

  return {
    groups: [],
    byGroup: {},
    hydrated: false,

    hydrate: () => {
      const local = readLocalEnvelope<Persisted>(BOT_GROUPS_KEY);
      const { groups, byGroup } = sanitizePersisted(local?.data);
      set({ groups, byGroup, hydrated: true });
      void syncFromServer();
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

    removeMember: (botId) => {
      const all = get().groups;
      const groups = all
        .map((g) => (g.memberIds.includes(botId) ? { ...g, memberIds: g.memberIds.filter((id) => id !== botId) } : g))
        .filter((g) => g.memberIds.length > 0);
      const byGroup = { ...get().byGroup };
      for (const g of all) if (!groups.some((next) => next.id === g.id)) delete byGroup[g.id];
      commit(groups, byGroup);
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

    appendScheduled: (groupId, message) => {
      const list = get().byGroup[groupId] ?? [];
      if (list.some((m) => m.runId === message.runId)) return false;
      commit(get().groups, { ...get().byGroup, [groupId]: [...list, message] });
      return true;
    },

    setMessages: (groupId, messages) => {
      commit(get().groups, { ...get().byGroup, [groupId]: messages });
    },

    updateMessage: (groupId, id, patch, persistNow = true) => {
      const list = get().byGroup[groupId];
      if (!list) return;
      const byGroup = {
        ...get().byGroup,
        [groupId]: list.map((m) => (m.id === id ? { ...m, ...patch } : m)),
      };
      commit(get().groups, byGroup, persistNow);
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
  // Another tab wrote a newer document — adopt it instead of waiting for a
  // reload. The storage event only fires in OTHER tabs, so this cannot loop.
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const onStorage = (event: StorageEvent) => {
      if (event.key === null || event.key === BOT_GROUPS_KEY) hydrate();
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, [hydrate]);
}

'use client';

// ── Conversation persistence ─────────────────────────────────────────────────
// The ChatBot transcript store's durability lives here, out of the SPA shell
// (which is pinned at its size budget): the instant localStorage cache is read
// on boot, the server transcript is hydrated + merged over it, and every change
// is mirrored back to the server (debounced). Extracted behavior-preserving from
// `stock-chat.tsx`; the shell keeps only the refs and setters it already owns.

import { useEffect, useRef } from 'react';
import {
  CONVERSATIONS_STORAGE_KEY,
  mostRecentConversation,
  normalizeConversations,
  saveConversationsCache,
  type Conversation,
} from './chat-organization';
import {
  deleteServerConversation,
  listServerConversations,
  saveServerConversation,
} from './transcript-client';
import { useWorkspaceStore } from '../agent-workspace/store';
import { restoreWorkspaceForChat } from '../agent-workspace/restore';
import type { Message } from '@/types/chat';

export interface ConversationPersistenceOptions {
  /** False until the shell has mounted (SSR-safe gate). */
  mounted: boolean;
  /** The live transcript list (dependency of the server mirror). */
  conversations: Conversation[];
  /** Synchronous mirror of `conversations` the async handlers read post-await. */
  conversationsRef: { current: Conversation[] };
  /** Synchronous mirror of the active conversation id. */
  activeConversationIdRef: { current: string | null };
  setConversations: (updated: Conversation[]) => void;
  setActiveConversationId: (id: string | null) => void;
  setMessages: (messages: Message[]) => void;
  /** Loads folders / colors / pin / rename from the organization store. */
  loadOrganization: () => void;
}

export function useConversationPersistence(opts: ConversationPersistenceOptions): void {
  const {
    mounted,
    conversations,
    conversationsRef,
    activeConversationIdRef,
    setConversations,
    setActiveConversationId,
    setMessages,
    loadOrganization,
  } = opts;

  // Server transcript sync. `serverHydratedRef` gates the diff-sync until the
  // first successful server load (so a failed load cannot delete server rows).
  // `syncedRef` remembers the last serialized form we pushed per conversation id.
  const serverHydratedRef = useRef(false);
  const syncedRef = useRef<Map<string, string>>(new Map());

  // Load conversations + folders from local storage.
  useEffect(() => {
    if (!mounted) return;
    loadOrganization();
    const saved = localStorage.getItem(CONVERSATIONS_STORAGE_KEY);
    if (saved) {
      try {
        // Normalize on load: backfills createdAt + folder/color/pin fields on
        // legacy rows so older transcripts gain organization support cleanly.
        const parsed = normalizeConversations(JSON.parse(saved));
        conversationsRef.current = parsed;
        setConversations(parsed);
        // Open the most recently active chat, not the first stored one.
        const start = mostRecentConversation(parsed);
        if (start) {
          activeConversationIdRef.current = start.id;
          setActiveConversationId(start.id);
          setMessages(start.messages);
          void restoreWorkspaceForChat(start.messages, start.id);
        } else {
          activeConversationIdRef.current = null;
          setActiveConversationId(null);
          setMessages([]);
          useWorkspaceStore.getState().clear();
        }
      } catch (err) {
        console.error('Error loading conversations:', err);
      }
    } else {
      conversationsRef.current = [];
      setConversations([]);
      activeConversationIdRef.current = null;
      setActiveConversationId(null);
      setMessages([]);
      useWorkspaceStore.getState().clear();
    }
  }, [mounted, loadOrganization]);

  // Server transcripts are the durable copy. localStorage is origin-scoped, so
  // closing the server or opening the app from a different origin silently lost
  // every chat; the Python runtime kept the runs but the UI could not read a
  // transcript back. On boot, hydrate from the server and merge it with the
  // local cache: the server wins for ids it has, local-only conversations are
  // kept and pushed up. localStorage remains the instant first paint above.
  useEffect(() => {
    if (!mounted) return;
    let cancelled = false;
    (async () => {
      try {
        const server = await listServerConversations();
        if (cancelled) return;
        const serverIds = new Set(server.map((c) => c.id));
        const local = conversationsRef.current;
        const localOnly = local.filter((c) => !serverIds.has(c.id));
        // Union by id; prefer the most recent activity, keeping the local copy on
        // a tie (it may carry an un-synced organization edit we push up).
        const byId = new Map<string, Conversation>();
        for (const c of [...server, ...local]) {
          const prev = byId.get(c.id);
          if (!prev || (c.timestamp ?? 0) > (prev.timestamp ?? 0)) byId.set(c.id, c);
        }
        const merged = [...byId.values()].sort((a, b) => (b.timestamp ?? 0) - (a.timestamp ?? 0));
        conversationsRef.current = merged;
        setConversations(merged);
        // Seed the sync ledger with what the server already holds, then push the
        // conversations that exist only locally (first-run migration).
        for (const c of merged) syncedRef.current.set(c.id, JSON.stringify(c));
        for (const c of localOnly) void saveServerConversation(c);
        serverHydratedRef.current = true;
        // Refresh the OPEN transcript from the merged (durable) copy. The
        // localStorage first paint above can be stale: it is origin-scoped and
        // silently stops updating once the whole transcript list outgrows the
        // quota (`setItem` throws QuotaExceededError, swallowed above), so the
        // cache keeps returning an old snapshot. Without this, a restart/refresh
        // showed that stale transcript until the user switched chats, even
        // though the server already held the new turns.
        const currentId = activeConversationIdRef.current;
        const active = currentId ? merged.find((c) => c.id === currentId) : null;
        if (active) {
          setMessages(active.messages);
          void restoreWorkspaceForChat(active.messages, active.id);
        } else {
          const start = mostRecentConversation(merged);
          if (start) {
            activeConversationIdRef.current = start.id;
            setActiveConversationId(start.id);
            setMessages(start.messages);
            void restoreWorkspaceForChat(start.messages, start.id);
          } else {
            activeConversationIdRef.current = null;
            setActiveConversationId(null);
            setMessages([]);
            useWorkspaceStore.getState().clear();
          }
        }
        // Evicts the least valuable chats rather than freezing the cache when
        // the merged list exceeds the quota (the server copy is authoritative).
        saveConversationsCache(localStorage, merged);
      } catch {
        // Runtime unavailable: stay local-only; the cache still works this session.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [mounted]);

  // Mirror conversation changes to the server (debounced). Upserts always run so
  // a conversation is durable even if the initial hydration failed or was slow;
  // the DELETE pass is gated on a successful load so a failed load can never
  // trigger spurious deletions of the server's own rows.
  useEffect(() => {
    if (!mounted) return;
    const timer = setTimeout(() => {
      const list = conversationsRef.current;
      const seen = new Set<string>();
      for (const c of list) {
        seen.add(c.id);
        const signature = JSON.stringify(c);
        if (syncedRef.current.get(c.id) === signature) continue;
        syncedRef.current.set(c.id, signature);
        void saveServerConversation(c).catch(() => {
          // A failed write must be retried on the next change.
          syncedRef.current.delete(c.id);
        });
      }
      if (!serverHydratedRef.current) return;
      for (const id of [...syncedRef.current.keys()]) {
        if (seen.has(id)) continue;
        syncedRef.current.delete(id);
        void deleteServerConversation(id).catch(() => undefined);
      }
    }, 700);
    return () => clearTimeout(timer);
  }, [conversations, mounted]);
}

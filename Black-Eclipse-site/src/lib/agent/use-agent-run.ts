'use client';

// ── useAgentRun — the React adapter over the conversation-scoped run manager ─
//
// This hook used to own the stream and refuse a second run. The manager
// (`run-manager.ts`) now owns streams by conversation, so this hook only
// selects one conversation's slice and forwards actions. A run keeps streaming
// while the user switches conversations or another chat surface mounts.

import { useCallback, useEffect, useMemo, useRef, useSyncExternalStore } from 'react';
import {
  runManager,
  type RunSnapshot,
  type StartRunArgs,
} from './run-manager';
import { ChatRequestError } from './registry';
import type { AssistantTurn } from './response-model';

export { ChatRequestError };
export type { StartRunArgs };

export interface UseAgentRunOptions {
  /**
   * Optional fallback turn sink for a surface that starts runs without passing
   * a per-run `onTurn`. The manager also calls the per-run sink, so passing
   * both would deliver each update twice.
   */
  onTurn?: (turn: AssistantTurn) => void;
  /** The conversation this hook selects. */
  chatId?: string;
}

export interface UseAgentRun {
  turn: AssistantTurn;
  active: boolean;
  runId: string | null;
  start: (args: StartRunArgs) => Promise<AssistantTurn>;
  /** Stop the in-flight run for this conversation. */
  cancel: () => void;
  decide: (approve: boolean, remember?: boolean) => Promise<void>;
  answer: (answer: string) => Promise<void>;
  reset: () => void;
}

/** Conversations with a live run, for sidebar badges (no token re-renders). */
export function useRunningConversationIds(): string[] {
  const key = useSyncExternalStore(
    runManager.subscribeLifecycle,
    runManager.getActiveKey,
    runManager.getActiveKey,
  );
  return useMemo(() => (key ? key.split('|') : []), [key]);
}

export function useAgentRun(options: UseAgentRunOptions = {}): UseAgentRun {
  const chatId = options.chatId ?? null;
  const onTurnRef = useRef(options.onTurn);
  onTurnRef.current = options.onTurn;

  const snapshot: RunSnapshot = useSyncExternalStore(
    runManager.subscribe,
    () => runManager.get(chatId),
    () => runManager.get(chatId),
  );

  // A reload/switch reattaches the conversation's live run exactly once.
  useEffect(() => {
    runManager.focus(chatId);
    if (chatId) runManager.reattach(chatId);
  }, [chatId]);

  const start = useCallback(
    (args: StartRunArgs): Promise<AssistantTurn> =>
      runManager.start({
        ...args,
        chatId: args.chatId ?? chatId ?? undefined,
        reasoningEffort: args.reasoningEffort,
        onTurn: args.onTurn ?? onTurnRef.current,
      }),
    [chatId],
  );

  const cancel = useCallback(() => {
    runManager.cancel(chatId);
  }, [chatId]);

  const decide = useCallback(
    (approve: boolean, remember = false) => runManager.decide(chatId, approve, remember),
    [chatId],
  );

  const answer = useCallback(
    (value: string) => runManager.answer(chatId, value),
    [chatId],
  );

  const reset = useCallback(() => {
    runManager.reset(chatId);
  }, [chatId]);

  // Keep the public shape identical to the previous hook. `turn` is the latest
  // snapshot; a surface that needs streaming writes should use `onTurn`.
  return {
    turn: snapshot.turn,
    active: snapshot.active,
    runId: snapshot.runId,
    start,
    cancel,
    decide,
    answer,
    reset,
  };
}

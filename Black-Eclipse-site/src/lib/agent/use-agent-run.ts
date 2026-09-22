'use client';

// ── useAgentRun — the one place a chat turn's lifecycle lives ───────────────
// Both chat surfaces (the ChatBot tab and the floating dock) used to duplicate
// streaming state inside their send handlers: a local accumulator, a status
// string, and a full message-array rewrite per token. This hook owns that
// lifecycle once, driven by the typed events from `./events`.
//
// It does not own the transcript. The host hands in history + the new prompt,
// receives an `AssistantTurn` on every meaningful change, and persists it in
// whatever store it uses. That keeps the two surfaces' storage unchanged while
// sharing the streaming logic.

import { useCallback, useEffect, useRef, useState } from 'react';
import { getAgentProvider } from './registry';
import type { ChatMessage } from './types';
import type { HarnessUiEvent } from './events';
import type { ActivityItem, AssistantTurn } from './response-model';
import { emptyTurn } from './response-model';

export interface StartRunArgs {
  /** Conversation turns BEFORE the new user message (role + content). */
  history: { role: 'user' | 'assistant'; content: string }[];
  /** The new user prompt. */
  userText: string;
  /** Workspace/session id, so the run's output is persisted server-side. */
  chatId?: string;
}

export interface UseAgentRunOptions {
  /**
   * Called with the updated turn on every meaningful change (a rAF-coalesced
   * text update, an activity change, or a terminal state). The host maps this
   * onto its message store.
   */
  onTurn?: (turn: AssistantTurn) => void;
}

export interface UseAgentRun {
  turn: AssistantTurn;
  active: boolean;
  runId: string | null;
  start: (args: StartRunArgs) => Promise<AssistantTurn>;
  /** Stop the in-flight run: abort the stream and ask the runtime to cancel. */
  cancel: () => void;
  reset: () => void;
}

export function useAgentRun(options: UseAgentRunOptions = {}): UseAgentRun {
  const [turn, setTurn] = useState<AssistantTurn>(emptyTurn);
  const [active, setActive] = useState(false);
  const [runId, setRunId] = useState<string | null>(null);

  // The authoritative mutable turn. React state is a projection of this so a
  // rAF flush always publishes the latest text without re-running the reducer.
  const turnRef = useRef<AssistantTurn>(emptyTurn());
  const abortRef = useRef<AbortController | null>(null);
  const activeRef = useRef(false);
  const rafRef = useRef<number | null>(null);
  const mountedRef = useRef(true);
  const onTurnRef = useRef(options.onTurn);
  onTurnRef.current = options.onTurn;

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
      abortRef.current?.abort();
    };
  }, []);

  const publish = useCallback((immediate: boolean) => {
    const emit = () => {
      rafRef.current = null;
      if (!mountedRef.current) return;
      const snapshot: AssistantTurn = { ...turnRef.current, activities: [...turnRef.current.activities] };
      setTurn(snapshot);
      onTurnRef.current?.(snapshot);
    };
    if (immediate) {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
      emit();
      return;
    }
    // Text deltas coalesce to one render per frame — a run of tokens must not
    // cause a state update (and Markdown re-parse) per character.
    if (rafRef.current == null) rafRef.current = requestAnimationFrame(emit);
  }, []);

  const applyEvent = useCallback(
    (event: HarnessUiEvent) => {
      const t = turnRef.current;
      switch (event.kind) {
        case 'status': {
          t.status = event.status;
          publish(true);
          break;
        }
        case 'delta': {
          if (t.status !== 'streaming') t.status = 'streaming';
          t.text += event.text;
          publish(false);
          break;
        }
        case 'activity_start': {
          t.activities.push({ ...event.item });
          publish(true);
          break;
        }
        case 'activity_end': {
          // Correlate by id, else fall back to the most recent still-running
          // item with the same name (retrieval events have no toolCallId).
          let idx = -1;
          if (event.id) idx = t.activities.findIndex((a) => a.id === event.id);
          if (idx === -1) {
            for (let i = t.activities.length - 1; i >= 0; i -= 1) {
              const a = t.activities[i];
              if (a.name === event.name && a.status === 'running') {
                idx = i;
                break;
              }
            }
          }
          if (idx !== -1) {
            const item: ActivityItem = {
              ...t.activities[idx],
              status: event.status,
              durationMs: event.durationMs ?? t.activities[idx].durationMs,
              code: event.code ?? t.activities[idx].code,
            };
            t.activities[idx] = item;
          } else {
            t.activities.push({
              id: event.id ?? `end:${event.name}`,
              kind: 'tool',
              name: event.name,
              label: event.name,
              status: event.status,
              durationMs: event.durationMs,
              code: event.code,
            });
          }
          publish(true);
          break;
        }
        case 'final': {
          if (event.output) t.finalText = event.output;
          if (event.error) {
            t.error = { message: event.error };
            t.status = 'error';
          } else {
            t.status = 'completed';
          }
          t.done = true;
          publish(true);
          break;
        }
        case 'error': {
          t.error = { code: event.code, message: event.message };
          t.status = 'error';
          t.done = true;
          publish(true);
          break;
        }
      }
    },
    [publish],
  );

  const start = useCallback(
    async (args: StartRunArgs): Promise<AssistantTurn> => {
      // Only one run at a time. A second `start` while active is a no-op that
      // returns the current turn, so a duplicate submit cannot orphan a stream.
      if (activeRef.current) return turnRef.current;
      activeRef.current = true;

      // Fresh turn for this request.
      turnRef.current = emptyTurn();
      turnRef.current.status = 'queued';
      publish(true);
      setActive(true);
      setRunId(null);

      const controller = new AbortController();
      abortRef.current = controller;

      const messages: ChatMessage[] = [
        ...args.history.map((m) => ({ role: m.role, content: m.content })),
        { role: 'user' as const, content: args.userText },
      ];

      try {
        const reply = await getAgentProvider().chat(messages, undefined, {
          chatId: args.chatId,
          signal: controller.signal,
          onRunId: (id) => {
            setRunId(id);
            if (mountedRef.current) onTurnRef.current?.({ ...turnRef.current });
          },
          onEvent: applyEvent,
        });

        const t = turnRef.current;
        // The provider may have already received `client.final`. If not (the
        // one-shot fallback fires no events), adopt the returned text.
        if (!t.done) {
          if (reply) {
            t.finalText = reply;
            t.status = 'completed';
          } else {
            t.status = 'cancelled';
          }
          t.done = true;
          publish(true);
        }
      } catch (err) {
        const t = turnRef.current;
        if (controller.signal.aborted || (err instanceof DOMException && err.name === 'AbortError')) {
          t.status = 'cancelled';
          if (!t.text && !t.finalText) {
            // A cancelled run with no partial text is still a valid empty turn.
          }
        } else {
          t.status = 'error';
          t.error = { message: err instanceof Error ? err.message : String(err) };
        }
        t.done = true;
        publish(true);
      } finally {
        abortRef.current = null;
        activeRef.current = false;
        if (mountedRef.current) setActive(false);
      }

      return turnRef.current;
    },
    [applyEvent, publish],
  );

  const cancel = useCallback(() => {
    const id = runId;
    abortRef.current?.abort();
    // Ask the runtime to stop cooperatively too (the abort only stops the
    // client from reading; the run must be told to stop producing).
    if (id) {
      void fetch(`/api/harness/runs/${encodeURIComponent(id)}/cancel`, { method: 'POST' }).catch(
        () => undefined,
      );
    }
  }, [runId]);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    activeRef.current = false;
    turnRef.current = emptyTurn();
    setTurn(emptyTurn());
    setActive(false);
    setRunId(null);
  }, []);

  return { turn, active, runId, start, cancel, reset };
}

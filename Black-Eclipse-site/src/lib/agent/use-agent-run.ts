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
import type { AssistantTurn, PendingApproval } from './response-model';
import { emptyTurn } from './response-model';
import { endActivity, initialActivityState, startActivity } from './activity-reducer';
import { sound } from '@/lib/sounds';
import { ALERT_NOTIFY_EVENT } from '@/lib/alerts/browser-notifier';
import { getUiFocus } from '@/lib/ui-engineering/ui-focus';

export interface StartRunArgs {
  /** Conversation turns BEFORE the new user message (role + content). */
  history: { role: 'user' | 'assistant'; content: string }[];
  /** The new user prompt. */
  userText: string;
  /** Workspace/session id, so the run's output is persisted server-side. */
  chatId?: string;
  /** The composer's model choice for this turn (overrides the saved model). */
  model?: string;
  /** The composer's per-question reasoning-effort override (overrides the saved
   *  default; absent = Auto). */
  reasoningEffort?: import('./reasoning').ReasoningLevel;
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
  /**
   * Answer the current approval card. Resolves the paused run in place; the
   * card clears immediately and a failed POST restores it so the user can retry.
   * `remember` additionally creates a standing grant ("Always allow").
   */
  decide: (approve: boolean, remember?: boolean) => Promise<void>;
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
  // Activity instance bookkeeping (unique ids + start→end correlation). Kept in
  // a ref so the reducer state survives the rAF-coalesced publishes.
  const activityStateRef = useRef(initialActivityState());

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
          const state = activityStateRef.current;
          startActivity(state, event.item);
          t.activities = [...state.activities];
          publish(true);
          break;
        }
        case 'activity_end': {
          const state = activityStateRef.current;
          endActivity(state, {
            id: event.id,
            name: event.name,
            status: event.status,
            durationMs: event.durationMs,
            code: event.code,
            summary: event.summary,
          });
          t.activities = [...state.activities];
          publish(true);
          break;
        }
        case 'final': {
          if (event.output) t.finalText = event.output;
          if (event.research) t.research = event.research;
          if (event.memory) t.memory = event.memory;
          if (event.runId) t.runId = event.runId;
          if (event.model) t.model = { model: event.model, provider: event.provider ?? null };
          if (event.codeVerification) t.codeVerification = event.codeVerification;
          if (event.autonomy !== undefined) t.autonomy = event.autonomy;
          if (event.capability) t.capability = event.capability;
          if (event.vision) t.vision = event.vision;
          if (event.documents) t.documents = event.documents;
          t.pendingApproval = undefined;
          if (event.error) {
            t.error = { code: event.errorCode, message: event.error };
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
          t.pendingApproval = undefined;
          t.done = true;
          publish(true);
          break;
        }
        case 'approval_request': {
          // The run is blocked until the operator decides. Not terminal: the
          // stream stays open and the runtime resumes in place on approval.
          t.pendingApproval = event.approval;
          t.status = 'awaiting_approval';
          publish(true);
          // Make it impossible to miss: a distinct cue, an in-app toast, and (if
          // opted in) an OS notification — the same channel the alert system uses.
          sound.notification();
          if (typeof window !== 'undefined') {
            const grant = event.approval.grantPattern ? ' You can also allow it always.' : '';
            window.dispatchEvent(
              new CustomEvent(ALERT_NOTIFY_EVENT, {
                detail: {
                  title: 'Approval needed',
                  body: `${event.approval.title}.${grant}`,
                },
              }),
            );
          }
          break;
        }
        case 'approval_resolved': {
          // Clear only the card this event refers to (or any card when the
          // runtime did not name one), so a late event cannot drop a newer card.
          if (!event.id || t.pendingApproval?.id === event.id) t.pendingApproval = undefined;
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
      activityStateRef.current = initialActivityState();
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
          model: args.model,
          reasoningEffort: args.reasoningEffort,
          // The page the user is currently working on (if any), so the agent can
          // resolve "my widgets" to a concrete blueprint.
          uiContext: getUiFocus(),
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

  const decide = useCallback(
    async (approve: boolean, remember = false) => {
      const pending: PendingApproval | undefined = turnRef.current.pendingApproval;
      if (!pending) return;
      // Clear the card optimistically so the buttons cannot double-submit; the
      // runtime's `approval.resolved` event is the authoritative clear. Restore
      // it if the POST fails so the operator can retry.
      turnRef.current.pendingApproval = undefined;
      if (turnRef.current.status === 'awaiting_approval') turnRef.current.status = 'tool_running';
      publish(true);
      try {
        const res = await fetch(
          `/api/harness/mcp/approvals/${encodeURIComponent(pending.id)}/decide`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ approve, remember: approve && remember }),
          },
        );
        if (!res.ok) throw new Error(`decision failed (${res.status})`);
      } catch {
        if (!turnRef.current.done) {
          turnRef.current.pendingApproval = pending;
          turnRef.current.status = 'awaiting_approval';
          publish(true);
        }
      }
    },
    [publish],
  );

  const reset = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    activeRef.current = false;
    turnRef.current = emptyTurn();
    setTurn(emptyTurn());
    setActive(false);
    setRunId(null);
  }, []);

  return { turn, active, runId, start, cancel, decide, reset };
}

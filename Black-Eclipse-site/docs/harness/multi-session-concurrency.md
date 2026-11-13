---
title: Multi-session concurrency
status: Current
last-verified: 2026-11-12
owner: Agent runtime
scope: parallel chat conversations, per-run transport/model, workspace projection
---

# Multi-session concurrency

Eclipse supports **one live run per conversation, many conversations at once**.
Before this change the runtime could already execute concurrent runs, but the
chat client mounted a single `useAgentRun` and refused a second run while one
was active.

## Why it exists

- A demo (or real work) needs a second question answered while the first is
  still tool-looping.
- The runtime's run kernel is per-run (leases, event bus, `_active` registry),
  so concurrency was already safe at the run level.
- The client, not the runtime, was the bottleneck.

## Client ownership

| Concern | Owner | Invariant |
|---|---|---|
| Live streams | `src/lib/agent/run-manager.ts` | One `LiveRun` per `chatId`; `start()` for an already-active chat returns the existing turn |
| React selection | `src/lib/agent/use-agent-run.ts` | The hook selects one conversation; it does not own the stream and never aborts on unmount |
| Active-run recovery | `src/lib/agent/registry.ts` | `eclipse.activeRuns.v2` maps `chatId → { runId, at }` (v1 is migrated on read) |
| Queue ownership | `src/lib/chat/message-queue.ts` | Each `QueuedPrompt` carries its `chatId`; `use-chat-queue-drain.ts` drains the first prompt whose OWN chat is idle |
| Workspace projection | `src/lib/agent/run-focus.ts` | Only the focused conversation's run may bind/reset the single Agent Workspace |
| Sidebar badges | `runManager.subscribeLifecycle` | Start/finish notifications only — never one re-render per token |

The shell (`stock-chat.tsx`) passes a **per-run** `onTurn` sink. When a run
streams in a background conversation, its sink writes into that conversation's
transcript even if the user is looking at another one. The active chat's
`agentBusy` therefore does not block an idle conversation.

## Runtime ownership

The market gateway and MCP manager are process-wide singletons. Per-run values
used to be written onto them:

```python
market_gateway._bridge = bridge
mcp_manager.set_sampling_model_factory(factory)
```

Two concurrent runs overwrote each other. `python/harness/run_binding.py` puts
those values in `ContextVar`s instead:

- `bind_run(bridge=..., sampling_factory=...)` wraps the run body in both
  `service.run` and `service.run_background`.
- `market/gateway.py` and `market/streaming.py` read `current_bridge(fallback)`.
- `mcp/manager.py` reads `current_sampling_factory(fallback)` lazily per call.
- Child tasks inherit the context, so streams and tool workers keep the right
  transport/model.

`HARNESS_MAX_CONCURRENT_RUNS` remains the optional admission bound (default
`0` = unbounded). The client is the natural place for a per-user cap when one
is added.

## Provider quota admission

A provider's quota is real; Eclipse must not stampede it. The model path now
has one process-wide gate:

- **Shared credentials** — `model_runtime/credential_pool.get_credential_pool()`
  caches a pool per provider/key-set, so a 429 cooldown and key rotation are
  visible to every concurrent run. (`graph.py` and `gateway.py` no longer build a
  per-run pool.)
- **Async admission** — `RateLimitManager.acquire_slot()` uses a per-credential
  semaphore (FIFO) plus cooldown/RPM/TPM windows. `HARNESS_MODEL_CONCURRENCY`
  (default `2`; `0` = unbounded) is the per-provider/model/credential ceiling, so
  two configured keys get two independent slots.
- **Wait, don't fail** — `ModelRuntime.invoke` waits for the earliest credential
  reset / admission slot, emits `model.queued` (reason `credential_cooldown`,
  `rate_limit`, or `concurrency`), and honors a provider `Retry-After`.
  `HARNESS_MODEL_COOLDOWN_WAIT_S` (default `60`) bounds the wait; past it the run
  fails honestly with `RATE_LIMITED`.
- **Adaptive bound** — the default ceiling is conservative; operators can tune
  it per deployment. The gate lives in Python because automation, tasks, bots
  and delegation all reach the model through the same runtime.

## Cross-tab conversations

`src/lib/agent/tab-coordinator.ts` makes same-origin tabs coordinate:

- **One owner** — `withChatStartLock()` uses Web Locks
  (`eclipse-chat:<chatId>`, `ifAvailable`) to elect the tab that starts a run.
  A follower attaches to the same server run instead of starting a second one.
- **Shared record** — `eclipse.sharedRuns.v1` in `localStorage` stores
  `chatId → { runId, ownerTabId, at }`, so a reload/follower can find the run.
- **Live follower** — the owner broadcasts `run.started` / `run.snapshot`
  (throttled, plus a 5s heartbeat independent of rAF) / `run.done` on
  `BroadcastChannel('eclipse.chat.v1')`. A follower applies the same turn
  snapshot and polls `/api/harness/runs/{id}` as a fallback.
- **Follower actions** — cancel/approve/answer are plain HTTP calls by run id,
  so a follower can act without owning the stream. The per-chat queue treats a
  run owned by another tab as busy (`runManager.isBusy`).
- **Server truth** — `GET /sessions/{id}` now returns `activeRun` (newest
  non-terminal run for that `sessionId`), so a client that lost localStorage can
  still discover and attach to a live run.
- **Transcript merge** — `mergeConversations()` (client cache) and
  `writeTranscript()` (server copy) union messages by id instead of
  last-writer-wins. A terminal assistant turn beats a streaming placeholder.

## Durable prompt queue

`src/lib/chat/queue-store.ts` owns every conversation's waiting prompts:

- **Persistent** — `eclipse.promptQueues.v1` in `localStorage`; a queued prompt
  survives a reload or closing the tab. When storage is blocked, an in-memory
  book keeps the queue working for the session.
- **Cross-tab** — changes broadcast on `BroadcastChannel('eclipse.queue.v1')`
  and the `storage` event. `takeNextFor()` serializes dequeue with a per-chat
  Web Lock, so two tabs take different prompts instead of duplicating one.
- **Pause/resume** — each chat's queue has a `paused` flag. The queue panel's
  play/pause button flips it; a paused queue keeps accepting prompts but does
  not drain.
- **Boot resume** — the drain hook reads the persisted queue on mount and starts
  the first prompt whose conversation is idle and unpaused, so queued work
  resumes after a reload.
- **Per-chat visibility** — `useMessageQueue().items` spans conversations;
  the shell filters the panel to the active chat. Sending is explicit about the
  target chat, so a prompt can never drain into another conversation.

## Tests

- `src/lib/agent/run-manager.test.ts` — two chats run concurrently; a duplicate
  run for one chat is refused; the sidebar key lists both live chats.
- `src/lib/agent/run-focus.test.ts` — only the focused chat's run ingests.
- `src/lib/chat/message-queue.test.ts` — a prompt keeps its originating chat.
- `python/tests/test_run_binding.py` — two tasks keep their own bridge/model;
  MCP sampling refuses outside a run.
- `python/tests/test_execution_registry.py::test_concurrent_runs_keep_their_own_bridge`
  — two `service.run` calls keep their own callback transport.
- `python/tests/test_model_admission.py` — per-key concurrency is bounded, a
  `Retry-After` is honored, the wait is caller-bounded, and two runs share one
  credential cooldown.
- `src/lib/chat/chat-organization.test.ts` — cross-tab message union and the
  terminal-over-streaming rule.
- `src/lib/chat/queue-store.test.ts` — persistence, atomic dequeue, pause, and
  per-conversation clear.

## Known limits

- The gate bounds how Eclipse uses a provider quota; it cannot raise it. With
  every configured key cooling, a run waits up to the configured budget and then
  fails honestly with `RATE_LIMITED`.
- Web Locks / BroadcastChannel are per-origin. Multi-device coordination relies
  on the server-side `activeRun` lookup and would need the `ChatSession` claim
  (revision/owner) for a strict single-writer guarantee across devices.
- The Agent Workspace is a single projection by design. It follows the focused
  conversation; it does not merge two runs' tool activity.

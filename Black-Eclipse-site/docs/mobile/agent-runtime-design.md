---
title: Eclipse Mobile — Agent Runtime Design
status: Proposed
last-verified: 2026-11-12
---

# Agent runtime design

The runtime is the product. The UI is a projection of its state.

## 1. Invariants

1. A run row and its input message are committed **before** any provider request.
2. Every non-transient event is persisted with a per-run monotonic `seq`.
3. The UI can rebuild the visible thread from `messages` + `run_events` alone.
4. An effectful tool has a `tool_calls` row before it executes.
5. An approval is bound to `(tool_name, canonical_args_sha256)` and is single-use.
6. A crash never auto-replays an external action; the run becomes `interrupted`.
7. Cancellation is cooperative and reaches the provider stream and tool timeouts.
8. Provider keys never leave Rust.
9. A run has exactly one writer. Concurrent starts on the same thread are
   serialized by a per-thread lock plus an idempotency key.
10. Retries apply to transient failures only; read-only tools may retry, effectful
    tools may not.

## 2. State machine

```
                 ┌──────────── cancel ────────────┐
                 │                                ▼
CREATED ──► QUEUED ──► RUNNING ──► COMPLETED   CANCELLED
                 │        │
                 │        ├──► WAITING_APPROVAL ──► RUNNING
                 │        │            └──────────► FAILED (denied/expired)
                 │        └──► FAILED
                 └──► INTERRUPTED (no live task at boot / app killed)
```

Stored statuses: `created`, `queued`, `running`, `waiting_approval`, `completed`,
`failed`, `cancelled`, `interrupted`.

Legal transitions are enforced in one function (`RunStore::transition`), not
scattered across commands. A terminal status never changes except through an
explicit retry that creates a **new** run.

## 3. Domain objects

| Object | Key fields |
| --- | --- |
| `Bot` | `id`, `name`, `description`, `objective`, `avatar`, `model_provider`, `model_id`, `agent_preset`, `target` (`local_mobile`), `created_at`, `updated_at` |
| `BotGroup` | `id`, `name`, `avatar`, `created_at` |
| `GroupMember` | `group_id`, `bot_id`, `position` |
| `Thread` | `id`, `kind` (`bot`/`group`), `bot_id`, `group_id`, `title`, `last_message_at` |
| `Message` | `id`, `thread_id`, `role`, `author_bot_id`, `content`, `status`, `run_id`, `reply_to_id`, `meta` |
| `Run` | `id`, `thread_id`, `bot_id`, `group_id`, `turn_id`, `kind`, `status`, `trigger`, `provider`, `model`, `input`, `output`, `error_class`, `attempt`, `last_seq`, `created_at`, `finished_at` |
| `RunEvent` | `run_id`, `seq`, `type`, `at`, `data` |
| `ToolCall` | `id`, `run_id`, `step`, `index`, `name`, `args`, `args_digest`, `status`, `result`, `error_class` |
| `Approval` | `id`, `run_id`, `tool_call_id`, `kind`, `title`, `summary`, `effect`, `risk`, `args_digest`, `status`, `decision`, `remember`, `expires_at` |
| `Memory` | `id`, `bot_id`, `thread_id`, `scope`, `subject`, `content`, `source_run_id`, `importance`, `deleted_at` |
| `Schedule` | `id`, `bot_id`, `kind`, `cron`, `interval_seconds`, `run_at`, `timezone`, `enabled`, `misfire`, `catch_up_max`, `next_run_at`, `last_run_at` |

The canonical JSON shapes are in `packages/agent-contracts/schema/`. SQLite DDL is
in `data-model.md`.

## 4. Commands

All commands are `#[tauri::command] async fn ... -> Result<T, RuntimeError>`.
Errors serialize as `{ class, message, retryable, detail? }`.

### Bots, groups, threads

```
list_bots() -> Vec<BotSummary>
get_bot(bot_id) -> Bot
create_bot(input: NewBot) -> Bot
update_bot(bot_id, patch) -> Bot
delete_bot(bot_id) -> ()
duplicate_bot(bot_id) -> Bot
list_threads() -> Vec<ThreadSummary>
get_thread(thread_id) -> Thread
get_messages(thread_id, before: Option<String>, limit: u32) -> Page<Message>
delete_thread(thread_id) -> ()
list_groups() -> Vec<GroupSummary>
create_group(name, member_ids) -> BotGroup
update_group(group_id, patch) -> BotGroup
delete_group(group_id) -> ()
```

### Runs

```
start_bot_run(input: StartBotRun) -> StartResult
start_group_run(input: StartGroupRun) -> StartResult
get_run(run_id) -> Run
list_active_runs() -> Vec<Run>
get_run_events(run_id, after_seq: u64, limit: u32) -> Vec<RunEvent>
cancel_run(run_id) -> ()
```

```ts
interface StartBotRun {
  threadId: string;
  botId: string;
  text: string;
  clientMessageId: string;      // idempotency key
  attachmentIds?: string[];
  modelOverride?: { provider: string; model: string } | null;
}
```

`StartResult` returns immediately: `{ runId, userMessageId, assistantMessageId }`.
Execution continues on the runtime; the UI listens for events.

### Approvals and clarification

```
approve_action(approval_id, remember: bool) -> ()
reject_action(approval_id, reason: Option<String>) -> ()
answer_clarification(clarification_id, answer: String) -> ()
```

### Providers and settings

```
list_providers() -> Vec<ProviderInfo>            // configured, never keys
set_provider_config(provider, base_url?, model_default?) -> ProviderInfo
set_provider_key(provider, key: SecretInput) -> ProviderInfo   // write-only
delete_provider_key(provider) -> ()
test_provider(provider) -> ProviderProbe
get_settings() -> Settings
update_settings(patch) -> Settings
```

`SecretInput` accepts the key, writes it to secure storage, and returns only
`{ configured: true, hint: "…last4" }`. It is never echoed, logged or evented.

### Schedules and data

```
list_schedules() -> Vec<Schedule>
create_schedule(input) -> Schedule
update_schedule(id, patch) -> Schedule
delete_schedule(id) -> ()
run_bot_now(bot_id) -> StartResult
export_data(destination: ExportTarget) -> ExportResult
delete_all_data(confirm_phrase: String) -> ()
```

## 5. Events

Envelope (identical to the desktop runtime's shape so fixtures can be shared):

```json
{
  "v": 1,
  "id": "evt_<runId>_<seq>",
  "runId": "run_...",
  "seq": 42,
  "type": "model.delta",
  "at": "2026-11-12T18:04:21.512Z",
  "data": { "text": "The position " }
}
```

Emitted to the UI as two Tauri events:

| Tauri event | Payload | Purpose |
| --- | --- | --- |
| `run:event` | the envelope | one persisted, ordered event |
| `run:delta` | `{ runId, messageId, seq, text }` | transient text, coalesced ~50 ms |
| `run:changed` | `{ runId, status, errorClass? }` | cheap status updates |
| `approval:changed` | `{ approvalId, runId, status }` | badge/sheet refresh |
| `schedule:changed` | `{ scheduleId }` | list refresh |
| `data:changed` | `{ entity, id }` | list/thread invalidation |

Event vocabulary (v1):

| Type | Persisted | Data |
| --- | ---: | --- |
| `run.created` | yes | `{ trigger, threadId, botId }` |
| `run.started` | yes | `{ provider, model }` |
| `model.requested` | yes | `{ step }` |
| `model.delta` | **no** (transient) | `{ text }` |
| `message.checkpoint` | yes | `{ messageId, chars }` |
| `model.completed` | yes | `{ step, finishReason, usage? }` |
| `tool.requested` | yes | `{ toolCallId, name, argsPreview, risk, permission }` |
| `tool.completed` | yes | `{ toolCallId, durationMs, summary }` |
| `tool.failed` | yes | `{ toolCallId, errorClass, message }` |
| `approval.requested` | yes | the `PendingApproval` shape |
| `approval.resolved` | yes | `{ approvalId, approved, remember }` |
| `clarification.requested` | yes | `{ id, question, context, options, recommended, allowCustom }` |
| `clarification.answered` | yes | `{ id }` |
| `run.completed` | yes | `{ usage? }` |
| `run.failed` | yes | `{ errorClass, message }` |
| `run.cancelled` | yes | `{ reason? }` |
| `run.interrupted` | yes | `{ lastSeq, reason: "process_lost" }` |

Transient deltas consume a `seq` but are **not** written to `run_events`. The
assistant message text is checkpointed every ~512 characters or 1 second. Resume
therefore reads the message content plus persisted events; it never needs the lost
delta frames. This mirrors the desktop runtime, where `model.delta` is transient.

## 6. The run loop

```
start_bot_run(input):
  tx = begin()
  bot = load_bot(tx, input.botId)
  thread = ensure_thread(tx, kind=bot, bot)
  user_msg = insert_message(tx, role=user, client_msg_id=input.clientMessageId)
       ON CONFLICT (thread_id, client_msg_id) DO NOTHING
  if conflict: return existing run (idempotent)
  run = insert_run(tx, status=created, input, trigger=user)
  assistant_msg = insert_message(tx, role=assistant, status=streaming, run_id=run.id)
  commit(tx)
  emit run.created
  spawn execute(run, bot, thread, user_msg)

execute(run):
  transition(queued -> running)
  messages = assemble_context(run, bot, thread)      // §8
  tools = registry.for_bot(bot, settings)
  for step in 0..MAX_STEPS (8):
      if cancel.is_cancelled(): finish(cancelled)
      stream = provider.chat_stream(model, messages, tools, cancel)
      text = ""
      tool_calls = []
      for event in stream:
          TextDelta(t)       -> text += t; persist_checkpoint(throttled); emit run.delta
          ToolCallStart(c)   -> tool_calls.push(c)   // emit after policy check
          ToolCallArgs(c, d) -> append args
          Usage(u)           -> remember
          Error(e)           -> classify; maybe retry
      append assistant message text (finalize)
      if tool_calls.is_empty(): break
      for call in tool_calls:
          validate schema
          persist tool_call(status=pending, args, digest)
          decision = policy.decide(call, bot, settings)
          if decision == Deny: persist failed/FORBIDDEN; continue
          if decision == Ask:
              approval = insert_approval(pending, digest, expires=15m)
              transition(waiting_approval)
              emit approval.requested
              decision = await_decision(approval)   // durable, not in-memory only
              transition(running)
          if decision == Allow:
              result = execute_with_timeout(call)
              persist tool_call(completed/failed)
              emit tool.completed/tool.failed
              messages.push(tool_result)
  persist run.completed; emit; transition(completed)
```

`await_decision` must survive process death: the loop first re-reads the approval
row. If a decision already exists (`approved`/`denied`), it continues immediately.
If the process died while pending, boot reconciliation marks the run
`interrupted` and the approval `expired`; a new run is required.

### Provider retries

| Failure | Retry |
| --- | --- |
| Connect/TLS/timeout before any token | Yes, ≤ 3, exponential + jitter, honor `Retry-After` |
| 429 / 5xx | Yes, ≤ 3 |
| 401/403 | No; `provider_auth`; prompt for a key |
| 400 invalid request / context overflow | No; surface a fixable error |
| Stream breaks mid-answer | Yes only if **no** tool call was emitted; otherwise mark interrupted |
| Tool failure | Read-only: yes once. External action: **never** |
| Cancelled | No |

### Concurrency

- One active run per thread; a second start returns the active run id instead of
  creating a duplicate.
- Group turns run members with `max_concurrency = 2` by default (battery + rate
  limits), configurable in settings.
- Global cap: 3 active runs. Additional starts queue (`queued`) and show progress.

## 7. Approvals and clarification

An approval row is the **only** authorisation to execute. It stores:

```
id, run_id, tool_call_id, kind, title, summary, effect, risk,
tool_name, args_json, args_digest, grant_pattern?,
status (pending|approved|denied|expired|consumed),
decision, remember, created_at, expires_at, decided_at
```

Rules:

1. `args_digest = sha256(canonical_json(tool_name, args))`. The canonical form
   sorts keys and normalizes numbers/strings.
2. `approve` performs a compare-and-set:
   `UPDATE approvals SET status='approved', decision='allow'
    WHERE id=? AND status='pending' AND args_digest=?`.
   Zero rows changed → the approval is stale or tampered → deny with
   `approval_mismatch`.
3. Execution re-reads the row, recomputes the digest and compares it again.
4. After successful authorisation, `approved → consumed`; a second use is refused.
5. A denial is terminal for that tool call. It is never silently retried.
6. Expiry is checked on read and on resume.
7. "Always allow" creates a narrow standing grant derived from the tool's
   `grant_pattern`; it never grants a different tool or a wider argument set.

Clarification is the same pause mechanism with `kind = clarify` and an answer
payload instead of an allow/deny decision. The answer is bounded (2,000 chars)
and is appended to the tool result.

## 8. Context assembly

```
system:
  mobile runtime identity + honesty rules
  bot persona (name, purpose, standing objective)         ← reused wording from botPersona
  tool policy summary (only the tools actually available)
  memory block (top-k, each with "Remembered:" provenance)
  attachment block (extracted text, labelled by filename)
history:
  last N turns: 10 for 1:1, 8 for a group member          ← same windows as desktop
  (failed turns excluded; group turns prefixed with author name)
current user turn
```

Budget:

- No tokenizer dependency in v1. Use a conservative estimate
  `tokens ≈ chars / 4` with a 15% safety margin, and calibrate downward from
  provider-reported usage.
- Reserve 25% of the model context for the reply and tool results.
- Drop oldest history first, then oldest memory items, then truncate attachments
  with an explicit `[truncated]` marker.
- Never drop the persona, the current user turn or the honesty rules.
- If the request still exceeds the budget, fail with `provider_context_overflow`
  and a suggestion to start a new thread — do not silently send a broken prompt.

## 9. Group orchestration

A group turn is a **turn**, not a run:

```
turn_id = uuid()
user message appended to the group thread once
for each addressed bot (all members, or those @mentioned):
    run = start_bot_run(thread=group, bot=member, parent_turn=turn_id, trigger=user)
    run_members(run_id, bot_id, turn_id)
```

- Each member gets its own `chat_id` / memory scope: `group-<groupId>-<botId>`.
- Each member sees the room transcript (author-labelled) as context, but replies
  only as itself.
- Replies stream into their own assistant messages in the room.
- A member failure does not cancel the others; the room shows per-member status.
- Group turns are capped at 6 members and 2 concurrent runs.
- The user turn is written once and is never duplicated by a catching-up member.

## 10. Tools

### Registry

Static, compiled in. Each tool declares a JSON Schema and a permission:

| Tool | Permission | Approval | Limits |
| --- | --- | --- | --- |
| `web_search` | read | no | 5 results, 8 KB total |
| `url_fetch` | read (network) | first host per run, then standing grant | 1 MB, 10 s, HTML→text |
| `remember` | write (local) | no | 2,000 chars |
| `recall` | read (local) | no | 20 items |
| `conversation_search` | read (local) | no | 20 hits |
| `read_attachment` | read (local) | no | 200 KB text / page cap |
| `group_context` | read (local) | no | current room only |

No shell, Python, JS, dynamic downloads, arbitrary filesystem, or network to a
private address.

### Validation

1. Parse arguments against the tool schema; reject unknown fields.
2. Enforce size and depth limits before execution.
3. Normalize and digest the arguments for approval binding.
4. Run with a timeout and an output cap.
5. Persist the bounded result; truncate with a marker, never drop silently.
6. Redact secrets from results before persistence.

### Policy

`Permission::Read` (local) runs without approval. Network reads require a
per-host approval the first time per run, then a standing grant scoped to the
host. `Write` (memory/notes) is local and reversible; it does not require
approval, but it is visible and deletable. There are no `ExternalAction` tools in
v1; the enum exists so a future tool cannot be added without a policy decision.

## 11. Provider adapters

```rust
#[async_trait]
pub trait Provider: Send + Sync {
    fn id(&self) -> &'static str;
    fn supports_tools(&self, model: &str) -> bool;
    async fn chat_stream(
        &self,
        request: ChatRequest,
        sink: &mut dyn ProviderSink,
        cancel: CancellationToken,
    ) -> Result<Usage, ProviderError>;
}

pub struct ChatRequest {
    pub model: String,
    pub system: String,
    pub messages: Vec<ProviderMessage>,
    pub tools: Vec<ToolSchema>,
    pub temperature: Option<f32>,
    pub max_tokens: Option<u32>,
}

pub enum ProviderEvent {
    TextDelta(String),
    ToolCallStart { index: u32, id: String, name: String },
    ToolCallArgs { index: u32, delta: String },
    ToolCallEnd { index: u32 },
    Usage { input: u64, output: u64 },
    Finish { reason: FinishReason },
}
```

Adapters in v1: `openai` (also used for OpenRouter-compatible endpoints),
`anthropic`, `google`. OpenRouter is configured as an OpenAI-compatible base URL
with its own headers; it is not a fourth code path.

Per-provider notes:

- **OpenAI/OpenRouter**: SSE `data:` frames; tool calls arrive as deltas with an
  `index`; `finish_reason=tool_calls`; `usage` may be absent on stream.
- **Anthropic**: SSE event types (`content_block_start`, `content_block_delta`,
  `message_stop`); tool input is a JSON delta string; system prompt is a separate
  field; required `anthropic-version` header.
- **Google**: streaming JSON chunks; function-call parts are complete rather than
  delta-based; map them to `ToolCallStart + Args + End` in one go.

Every adapter must pass the same fixture suite (recorded frames) and expose the
same error classes.

## 12. Memory

- Explicit memories only in v1 (`remember` tool or a user "remember this" action).
- Scope is the bot's conversation bucket; `group-<gid>-<bid>` is private to that
  member.
- Retrieval: FTS5 over `memories.content` filtered by `bot_id`, ranked by
  `bm25` then recency then importance.
- Provenance is preserved: `source_run_id`, `created_at`, and a visible
  "Remembered" label in the transcript.
- Deletion is immediate (soft-delete + FTS rebuild on demand); export includes
  memories unless the user excludes them.
- No embeddings, no evidence graph, no background consolidation in v1.

## 13. Crash recovery and boot reconciliation

On every app start, before the UI is interactive:

```
for run in runs where status in (created, queued, running, waiting_approval):
    if run.owner_pid == current_pid and run.started_this_session: continue
    if run.status == waiting_approval and approval.status == pending:
        approval.status = expired
    transition(run, interrupted)
    append_event(run, "run.interrupted", { lastSeq, reason: "process_lost" })
    finalize_streaming_messages(run, status=interrupted)
    recompute(schedules)
```

A `owner_pid`/`boot_id` pair prevents a second process (or a WebView reload) from
declaring a live run dead.

## 14. Error taxonomy

| Class | Retryable | UI treatment |
| --- | ---: | --- |
| `provider_auth` | no | "Key rejected" → open provider settings |
| `provider_rate_limit` | yes | countdown; automatic retry |
| `provider_unavailable` | yes | "Provider unreachable" + retry |
| `provider_timeout` | yes | retry once, then fail |
| `provider_context_overflow` | no | start a new thread / trim attachments |
| `tool_invalid_arguments` | no | show the tool and the schema error |
| `tool_timeout` | read-only yes | retry affordance |
| `tool_forbidden` | no | explain the policy |
| `approval_denied` | no | the card stays with the denial |
| `approval_expired` | no | re-run to request again |
| `approval_mismatch` | no | security event; deny and log |
| `storage` | yes once | "Could not save"; never lose the message |
| `cancelled` | no | normal stop state |
| `interrupted` | no | "Run stopped when the app closed" + retry |
| `internal` | no | redacted message + log id |

## 15. Limits (v1)

| Limit | Value |
| --- | --- |
| Max steps per run | 8 |
| Max tool calls per step | 6 |
| Max tool calls per run | 24 |
| Max concurrent runs | 3 (group member concurrency 2) |
| Max input tokens (estimated) | model context × 0.75 |
| Max attachment text per turn | 60,000 chars total |
| Max message characters | 100,000 |
| Max approval lifetime | 15 min |
| Max scheduled catch-up | 3 runs per bot per open |
| Retry attempts | 3 |

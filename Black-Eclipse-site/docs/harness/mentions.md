---
title: Mentions — `@` a bot or group chat
status: Current
last-verified: 2026-10-15
---

# Mentions — `@` a bot or group chat

**Who this is for:** anyone changing how a bot or group chat is `@`-mentioned
from the main chat composer, or how a mentioned turn is delegated.

## What this is (and why)

The `@` mention is the sibling of the [slash command](./slash-commands.md). Where
a leading `/` names a command, a leading (or mid-text) `@Name` names one of the
user's **bots** or **group chats**. It exists so the main Eclipse chat can reach
the user's own agents and rooms without leaving the conversation: a mentioned turn
is **delegated** to the real bot/room, and its reply streams into the same
transcript, attributed to whoever produced it.

The distinction that keeps the design honest:

- **A delegation is a normal run.** The bot/room answers through the same
  streaming agent provider (`getAgentProvider().chat` →
  `/api/harness/chat/stream` → the Python runtime) that the Bots workspace
  already uses. There is no second agent loop, no TS-side tool registry, and nothing
  is fabricated. If the runtime is down, the delegated turn fails honestly like
  any other run.
- **Memory stays per-conversation.** A bot turn binds the run's conversation id to
  `bot-<id>` and a room member's to `group-<gid>-<botid>` (the existing
  `conversation` memory scope), so a bot recalled in the main chat shares the same
  private memory as its own thread.
- **Rooms never merge voices.** `@GroupName` has each member answer in its own
  voice into its own message — exactly the behavior of the Bots-tab room.

## The contract (pure module)

`src/lib/bots/mentions.ts` is the ONE registry + parser. It owns no execution and
no I/O, so the composer palette and the dispatcher can never disagree about who is
mentionable.

- `MentionTarget` — a union over `{ kind: 'bot' | 'group'; id; name; description;
  memberIds }`.
- `buildMentionTargets(bots, groups)` — the pure projection from the live
  `AutomationView[]` and `BotGroup[]`. Unnamed records contribute nothing.
- `searchMentions(targets, query, limit)` — deterministic
  prefix/name/description/fuzzy ranking for the palette.
- `parseMentions(text, targets)` / `mentionedTargets(text, targets)` — resolve every
  `@Name` in a message. Names match case-insensitively and **longest-first** (so
  `@Portfolio Bot` beats `@Portfolio`); the `@` must start the text or follow
  whitespace (never inside an email); the name must end on a word boundary (so
  `@Bob` does not match `@Bobby`); duplicates collapse to the first occurrence.

## The composer palette

`src/components/chat/chat-input.tsx` renders the `@` palette (portaled to `<body>`
like the `/` palette). Typing `@word` (no space yet) opens a menu of matching
targets with the bot/room avatar and a `bot`/`group` tag; selecting one inserts
`@Name ` and focuses the composer. Resolved mentions already in the draft show as
chips above the composer, so the user sees exactly which bots/rooms the message
will reach before sending. The palette is inert unless the host passes
`mentionTargets`.

## Delegation lifecycle

`src/lib/bots/use-bot-delegation.ts` owns the turn lifecycle and the mentionable
list (it hydrates the bot + group stores). On send:

1. The host routes the turn through `dispatchTurn` (`stock-chat.tsx`): if the text
   resolves to any `@mention`, it delegates; otherwise it runs the normal Eclipse
   agent. Every send path funnels through here — send, follow-up, edit/redirect and
   injected prompts.
2. Targets are expanded: a bot is one turn; a room is one turn per member.
3. Each turn is built and run by the shared invoker `src/lib/bots/invoke.ts`
   (`runBotTurn` / `runGroupMemberTurn`) — persona, recent-history window, private
   memory scope and chat-id scheme in one place, reused by `bot-chat.tsx` and
   `group-chat-room.tsx` too.
4. Replies stream into their own assistant messages, attributed via
   `Message.author` (`src/types/chat.ts`) and rendered with the author identity in
   `src/components/chat/chat-history.tsx`.
5. Stop aborts every in-flight delegated turn (the client stops reading and keeps
   the streamed text — the same contract as the Bots workspace).

## Where it is wired

- Palette + parsing: `src/components/chat/chat-input.tsx`, `src/components/chat/empty-state.tsx`.
- Routing: `dispatchTurn` in `src/components/screens/stock-chat.tsx`.
- Lifecycle: `src/lib/bots/use-bot-delegation.ts`.
- Shared run: `src/lib/bots/invoke.ts`.
- Attribution: `src/types/chat.ts` (`Message.author`), `src/components/chat/chat-history.tsx`.

## Bots-tab mirroring

A completed delegated exchange is also written into the bot's or room's own
thread (`useBotChatStore` / `useBotGroupsStore`), so the Bots tab reflects it — a
room's user turn is written once no matter how many members reply. Memory was
already shared via the run's `conversation` scope; the mirror is the visible
thread. It is written on **success** only (a failed delegated turn stays in the
main transcript as an honest error).

## Approvals mid-delegation

A bot/room turn can block on an operator approval. The invoker forwards the
typed harness events (`runBotTurn` / `runGroupMemberTurn` accept `onEvent`), so the
delegation hook sees `approval.requested` and sets `pendingApproval` on that
turn's message — the main chat's existing `ApprovalCard` then renders it for free.
The decision is routed to the delegation hook (`useBotDelegation.decide`) when the
pending approval belongs to a delegated turn, and to `useAgentRun.decide` when it
belongs to the main run; both POST the single-use
`/api/harness/mcp/approvals/{id}/decide` and restore the card on failure.

## Not (yet) built

- Only the most recent delegated approval is tracked at a time; a batch that
  raises several blocking approvals simultaneously surfaces them one at a time.
- A delegated turn streams into the main transcript only (it is not rendered
  live inside the Bots-tab thread; that thread receives the finished exchange).

## Tests

`src/lib/bots/mentions.test.ts` — target projection, search ranking, longest-name
resolution, word-boundary and email safety, duplicate collapse.

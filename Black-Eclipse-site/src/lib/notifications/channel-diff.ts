// ── Channel activity diffing ─────────────────────────────────────────────────
// Pure helper for the global channel watcher. The Python Channel Gateway owns
// the truth; the watcher polls `GET /api/channels/messages` and this module
// answers the only question that matters per poll: which INBOUND messages are
// new since the last one?
//
// First sight seeds the seen set (no replay on boot). Reply/outbound messages are
// ignored — the operator's own replies are not news. Kept framework-free and pure
// so it is unit-tested without a DOM.

export interface WatchedChannelMessage {
  id: string;
  kind: string;
  direction: string;
  text: string;
  status: string;
  createdAt?: string | null;
}

export interface ChannelNotification {
  /** Stable dedupe key: `channel:<messageId>`. */
  id: string;
  messageId: string;
  title: string;
  body: string;
}

const MAX_BODY = 120;

function titleFor(message: WatchedChannelMessage): string {
  switch (message.status) {
    case "confirmation_required":
      return "Confirmation needed";
    case "linked":
      return "Account linked";
    case "rate_limited":
      return "Remote user throttled";
    case "denied":
      return "Remote action denied";
    default:
      return `New ${message.kind} message`;
  }
}

function bodyFor(message: WatchedChannelMessage): string {
  const text = (message.text ?? "").trim().replace(/\s+/g, " ");
  return text.length > MAX_BODY ? `${text.slice(0, MAX_BODY)}…` : text;
}

/**
 * Compare the current feed against the previously-seen message ids and return
 * the notifications for NEW inbound messages, plus the next seen-id set.
 *
 * `seed` (the first poll) returns no notifications — opening the app never
 * replays history. The next set is exactly the current feed's ids, so it stays
 * bounded to the feed window.
 */
export function selectChannelActivity(
  messages: WatchedChannelMessage[],
  seen: Set<string>,
  opts: { seed: boolean },
): { notifications: ChannelNotification[]; next: Set<string> } {
  const next = new Set<string>();
  const notifications: ChannelNotification[] = [];

  for (const message of messages) {
    if (typeof message.id !== "string") continue;
    next.add(message.id);
    if (opts.seed) continue;
    if (message.direction !== "in") continue;
    if (seen.has(message.id)) continue;
    notifications.push({
      id: `channel:${message.id}`,
      messageId: message.id,
      title: titleFor(message),
      body: bodyFor(message),
    });
  }

  return { notifications, next };
}

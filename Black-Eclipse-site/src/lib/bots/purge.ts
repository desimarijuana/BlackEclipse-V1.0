// ── Bot / group deletion cleanup ─────────────────────────────────────────────
// Deleting a bot or room must not leave invisible private state behind. The
// runtime owns the durable memory buckets (`bot-<id>`, `group-<gid>-<bid>`); the
// client owns the thread, face and room membership. This module is the ONE
// place that clears both sides, best-effort and never blocking the delete.

'use client';

import { forgetConversation } from '@/lib/harness/eclipse-memory-browser';
import { useBotAvatarStore } from './avatar-store';
import { useBotChatStore } from './chat-store';
import { useBotGroupsStore } from './groups-store';

function conversationIdsForBot(botId: string): string[] {
  const ids = [`bot-${botId}`];
  for (const group of useBotGroupsStore.getState().groups) {
    if (group.memberIds.includes(botId)) ids.push(`group-${group.id}-${botId}`);
  }
  return ids;
}

/** Forget a bot's private memory (own thread + every room it belonged to). */
export async function forgetBotMemory(botId: string): Promise<void> {
  await Promise.all(
    conversationIdsForBot(botId).map((id) => forgetConversation(id).catch(() => undefined)),
  );
}

/** Forget every member's private memory for a room (each has its own bucket). */
export async function forgetGroupMemory(groupId: string, memberIds: readonly string[]): Promise<void> {
  await Promise.all(
    memberIds.map((botId) =>
      forgetConversation(`group-${groupId}-${botId}`).catch(() => undefined),
    ),
  );
}

/**
 * Remove a deleted bot from client state: its thread, its face/photo, and every
 * room membership. Runs synchronously so the UI cannot show a ghost row, and is
 * safe to call when the delete actually failed only if the caller then hydrates.
 */
export function forgetBotLocally(botId: string): void {
  useBotChatStore.getState().clear(botId);
  useBotAvatarStore.getState().resetAvatar(botId);
  useBotAvatarStore.getState().setImage(botId, null);
  useBotGroupsStore.getState().removeMember(botId);
}

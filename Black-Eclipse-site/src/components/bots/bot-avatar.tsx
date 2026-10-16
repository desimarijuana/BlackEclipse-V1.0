'use client';

// ── BotAvatar ────────────────────────────────────────────────────────────────
// The one place a bot's identity picture is rendered. Prefers an uploaded photo
// (data URL, stored on the client) and otherwise falls back to the deterministic
// ghost face. Every bot surface uses this so an uploaded photo and a customized
// face can never render inconsistently between the list, chat and sidebar.

import { cn } from '@/lib/utils';
import { GhostAvatar } from '@/components/bots/ghost-avatar';
import { LiveGhostAvatar } from '@/components/bots/live-ghost-avatar';
import { useBotAvatarStore } from '@/lib/bots/avatar-store';
import type { GhostSpec } from '@/lib/bots/ghost';
import type { GhostMood } from '@/lib/bots/ghost-mood';

export interface BotAvatarProps {
  botId: string;
  spec: GhostSpec;
  /** Rendered pixel size (square). Defaults to 48. */
  size?: number;
  className?: string;
  /** Accessible label; when set the picture exposes an image role. */
  title?: string;
  /**
   * Opt into the ambient animated face (blink / breathe). Off by default so
   * list rows and icons stay cheap and static. An uploaded photo is unaffected.
   */
  live?: boolean;
  /** Cursor gaze + click bounce; implies `live`. */
  interactive?: boolean;
  /** Only animate while on screen. Default true. */
  inViewOnly?: boolean;
  /** Face expression (only meaningful with `live`). */
  mood?: GhostMood;
}

export function BotAvatar({
  botId,
  spec,
  size = 48,
  className,
  title,
  live = false,
  interactive = false,
  inViewOnly = true,
  mood,
}: BotAvatarProps) {
  const image = useBotAvatarStore((s) => s.images[botId]);
  if (image) {
    return (
      <img
        src={image}
        alt={title ?? ''}
        width={size}
        height={size}
        className={cn('shrink-0 select-none rounded-full object-cover', className)}
        style={{ width: size, height: size }}
      />
    );
  }
  if (live || interactive) {
    return (
      <LiveGhostAvatar
        spec={spec}
        size={size}
        className={className}
        title={title}
        mood={mood}
        interactive={interactive}
        inViewOnly={inViewOnly}
      />
    );
  }
  return <GhostAvatar spec={spec} size={size} className={className} title={title} />;
}

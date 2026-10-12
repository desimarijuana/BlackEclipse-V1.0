'use client';

// ── BotAvatar ────────────────────────────────────────────────────────────────
// The one place a bot's identity picture is rendered. Prefers an uploaded photo
// (data URL, stored on the client) and otherwise falls back to the deterministic
// ghost face. Every bot surface uses this so an uploaded photo and a customized
// face can never render inconsistently between the list, chat and sidebar.

import { cn } from '@/lib/utils';
import { GhostAvatar } from '@/components/bots/ghost-avatar';
import { useBotAvatarStore } from '@/lib/bots/avatar-store';
import type { GhostSpec } from '@/lib/bots/ghost';

export interface BotAvatarProps {
  botId: string;
  spec: GhostSpec;
  /** Rendered pixel size (square). Defaults to 48. */
  size?: number;
  className?: string;
  /** Accessible label; when set the picture exposes an image role. */
  title?: string;
}

export function BotAvatar({ botId, spec, size = 48, className, title }: BotAvatarProps) {
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
  return <GhostAvatar spec={spec} size={size} className={className} title={title} />;
}

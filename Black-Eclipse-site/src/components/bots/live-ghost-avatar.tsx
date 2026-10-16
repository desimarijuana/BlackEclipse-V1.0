// ── LiveGhostAvatar ──────────────────────────────────────────────────────────
// The animated layer on top of the pure `GhostAvatar` drawing. The drawing never
// changes; this wrapper adds ambient life (blink / breathe) and, when asked,
// interactivity (the eyes follow the cursor; a click gives a little bounce).
//
// Cheap by construction: animation only runs while the face is on screen (an
// IntersectionObserver gates it), and all motion is CSS keyframes that the
// repo's existing reduce-motion / animations-off kill switches silence. Static
// `GhostAvatar` remains the right choice for lists, icons and rows.

'use client';

import { useEffect, useRef, useState } from 'react';
import { cn } from '@/lib/utils';
import { GhostAvatar, type GhostAvatarProps } from './ghost-avatar';
import { useGhostGaze } from '@/lib/bots/use-ghost-gaze';

export interface LiveGhostAvatarProps extends GhostAvatarProps {
  /** Eyes ease toward the cursor and a click gives a small bounce. */
  interactive?: boolean;
  /** Only animate while scrolled into view. Default true. */
  inViewOnly?: boolean;
}

export function LiveGhostAvatar({
  interactive = false,
  inViewOnly = true,
  className,
  mood,
  ...rest
}: LiveGhostAvatarProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const [active, setActive] = useState(!inViewOnly);
  const [poking, setPoking] = useState(false);

  useEffect(() => {
    if (!inViewOnly) return;
    const el = ref.current;
    if (!el || typeof IntersectionObserver === 'undefined') {
      setActive(true);
      return;
    }
    const io = new IntersectionObserver(
      (entries) => setActive(entries[0]?.isIntersecting ?? true),
      { rootMargin: '80px' },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [inViewOnly]);

  useGhostGaze(ref, interactive && active);

  useEffect(() => {
    if (!poking) return;
    const id = window.setTimeout(() => setPoking(false), 620);
    return () => window.clearTimeout(id);
  }, [poking]);

  return (
    <span
      ref={ref}
      className="be-ghost-live inline-flex"
      data-active={active ? '' : undefined}
      data-interactive={interactive ? '' : undefined}
      data-poke={poking ? '' : undefined}
      style={interactive ? { cursor: 'pointer' } : undefined}
      onClick={
        interactive
          ? () => {
              setPoking(false);
              requestAnimationFrame(() => setPoking(true));
            }
          : undefined
      }
    >
      <GhostAvatar
        {...rest}
        mood={active ? mood : undefined}
        className={cn('be-ghost--live', className)}
      />
    </span>
  );
}

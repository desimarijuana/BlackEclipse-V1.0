// ── Bot avatar store ────────────────────────────────────────────────────────
// Persists each bot's ghost face on the client, keyed by bot id. This is
// presentation-layer identity (how a bot looks), so it follows the repo's
// client-side persistence convention for appearance settings — the same
// approach as `lib/sidebar/store.ts` (hydrate on mount, write on change).
//
// A bot with no saved face gets a deterministic one derived from its id, so it
// looks the same on every device before the user customizes it.

'use client';

import { useEffect } from 'react';
import { create } from 'zustand';
import {
  createRng,
  ghostSpecFromId,
  normalizeGhostSpec,
  randomGhostSpec,
  type GhostSpec,
} from './ghost';

export const BOT_AVATAR_KEY = 'be_bot_avatars_v1';
/** Optional uploaded photo per bot, as a data URL. Takes precedence over the ghost face. */
export const BOT_AVATAR_IMAGE_KEY = 'be_bot_avatar_images_v1';

interface BotAvatarStore {
  /** Saved faces by bot id. Absent entries fall back to the id-derived face. */
  avatars: Record<string, GhostSpec>;
  /** Uploaded photos by bot id (data URLs). When present, shown instead of the face. */
  images: Record<string, string>;
  hydrated: boolean;
  hydrate: () => void;
  setAvatar: (botId: string, spec: GhostSpec) => void;
  setImage: (botId: string, dataUrl: string | null) => void;
  randomize: (botId: string) => GhostSpec;
  resetAvatar: (botId: string) => void;
}

function persist(avatars: Record<string, GhostSpec>) {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(BOT_AVATAR_KEY, JSON.stringify(avatars));
  } catch {
    /* quota / private mode — in-memory only */
  }
}

function persistImages(images: Record<string, string>) {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(BOT_AVATAR_IMAGE_KEY, JSON.stringify(images));
  } catch {
    /* quota / private mode — in-memory only */
  }
}

/** The face for a bot: its saved customization, else a deterministic default. */
export function avatarFor(avatars: Record<string, GhostSpec>, botId: string): GhostSpec {
  return avatars[botId] ?? ghostSpecFromId(botId);
}

export const useBotAvatarStore = create<BotAvatarStore>((setState, getState) => ({
  avatars: {},
  images: {},
  hydrated: false,

  hydrate: () => {
    let avatars: Record<string, GhostSpec> = {};
    let images: Record<string, string> = {};
    if (typeof window !== 'undefined') {
      try {
        const raw = localStorage.getItem(BOT_AVATAR_KEY);
        if (raw) {
          const parsed = JSON.parse(raw) as Record<string, unknown>;
          if (parsed && typeof parsed === 'object') {
            for (const [id, value] of Object.entries(parsed)) {
              avatars[id] = normalizeGhostSpec(value);
            }
          }
        }
      } catch {
        avatars = {};
      }
      try {
        const raw = localStorage.getItem(BOT_AVATAR_IMAGE_KEY);
        if (raw) {
          const parsed = JSON.parse(raw) as Record<string, unknown>;
          if (parsed && typeof parsed === 'object') {
            for (const [id, value] of Object.entries(parsed)) {
              if (typeof value === 'string' && value.startsWith('data:')) images[id] = value;
            }
          }
        }
      } catch {
        images = {};
      }
    }
    setState({ avatars, images, hydrated: true });
  },

  setAvatar: (botId, spec) => {
    const avatars = { ...getState().avatars, [botId]: normalizeGhostSpec(spec) };
    persist(avatars);
    setState({ avatars });
  },

  setImage: (botId, dataUrl) => {
    const images = { ...getState().images };
    if (dataUrl) images[botId] = dataUrl;
    else delete images[botId];
    persistImages(images);
    setState({ images });
  },

  randomize: (botId) => {
    const spec = randomGhostSpec(createRng());
    const avatars = { ...getState().avatars, [botId]: spec };
    persist(avatars);
    setState({ avatars });
    return spec;
  },

  resetAvatar: (botId) => {
    const next = { ...getState().avatars };
    delete next[botId];
    persist(next);
    setState({ avatars: next });
  },
}));

/** Hydrate bot faces from localStorage once, on the client. */
export function useHydrateBotAvatars() {
  const hydrate = useBotAvatarStore((s) => s.hydrate);
  const hydrated = useBotAvatarStore((s) => s.hydrated);
  useEffect(() => {
    if (!hydrated) hydrate();
  }, [hydrated, hydrate]);
}

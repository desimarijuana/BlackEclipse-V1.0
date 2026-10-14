'use client';

// ── Browser-tab indicator ───────────────────────────────────────────────────
// The red notification signal ON THE BROWSER TAB itself. Mounted once at the
// app root; subscribes to the notification ledger and, while anything is
// unread:
//   1. prefixes the tab title with the count (see `title.ts`) — every browser
//      shows this in the tab strip,
//   2. swaps the favicon for a red-badged copy canvas-composed from the live
//      icon (so a theme-customized favicon is respected), restoring the plain
//      icon the moment nothing is unread,
//   3. sets the OS/PWA app badge where the browser supports it (Chrome/Edge).
// No in-app icon, no panel — the ledger stays the one source of truth and the
// sidebar's tab badges remain the in-app surface.

import { useEffect, useRef } from 'react';
import { totalUnread, useNotificationsStore } from './store';
import { formatTabTitle, stripTabPrefix } from './title';

const FALLBACK_ICON = '/branding/FAVICON.svg';

function ensureIconLink(): HTMLLinkElement {
  let link = document.querySelector<HTMLLinkElement>('link[rel="icon"]');
  if (!link) {
    link = document.createElement('link');
    link.rel = 'icon';
    document.head.appendChild(link);
  }
  return link;
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error('icon load failed'));
    img.src = src;
  });
}

/** The live favicon with a red count badge composited on the top-right corner. */
async function makeBadgedIcon(baseHref: string, count: number): Promise<string | null> {
  try {
    const img = await loadImage(baseHref);
    const size = 64;
    const canvas = document.createElement('canvas');
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext('2d');
    if (!ctx) return null;
    ctx.drawImage(img, 0, 0, size, size);

    const label = count > 9 ? '9+' : String(count);
    const cx = 47;
    const cy = 17;
    const r = 16;
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.fillStyle = '#ef4444';
    ctx.fill();
    ctx.fillStyle = '#ffffff';
    ctx.font = `bold ${label.length > 1 ? 15 : 21}px Arial, sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(label, cx, cy + 1);

    return canvas.toDataURL('image/png');
  } catch {
    return null;
  }
}

function applyAppBadge(unread: number): void {
  const nav = navigator as Navigator & {
    setAppBadge?: (count?: number) => Promise<void>;
    clearAppBadge?: () => Promise<void>;
  };
  try {
    const result = unread > 0 ? nav.setAppBadge?.(unread) : nav.clearAppBadge?.();
    if (result && typeof result.catch === 'function') void result.catch(() => undefined);
  } catch {
    /* unsupported — the title + favicon already carry the signal */
  }
}

export function BrowserTabIndicator() {
  const items = useNotificationsStore((s) => s.items);
  const unread = totalUnread(items);
  // The pristine icon href (theme favicon or the shipped mark), remembered
  // whenever the link does not currently hold a badge WE applied.
  const baseIconRef = useRef<string>(FALLBACK_ICON);
  const badgedIconRef = useRef<string | null>(null);

  // Title: compose from the CURRENT base so a theme-applied brand name is
  // never clobbered, and stripping makes repeated runs idempotent.
  useEffect(() => {
    if (typeof document === 'undefined') return;
    const base = stripTabPrefix(document.title);
    document.title = formatTabTitle(base, unread);
  }, [unread]);

  // Favicon + OS app badge.
  useEffect(() => {
    if (typeof document === 'undefined') return;
    const link = ensureIconLink();
    const current = link.getAttribute('href') || '';
    // A href that is not our badge is the pristine source (custom favicon or
    // the shipped default) — remember it. Our badged data URL never becomes
    // the base.
    if (current && current !== badgedIconRef.current) baseIconRef.current = current;

    applyAppBadge(unread);

    if (unread <= 0) {
      link.href = baseIconRef.current;
      badgedIconRef.current = null;
      return;
    }

    let cancelled = false;
    void makeBadgedIcon(baseIconRef.current, unread).then((dataUrl) => {
      if (cancelled || !dataUrl) return;
      link.href = dataUrl;
      badgedIconRef.current = dataUrl;
    });
    return () => {
      cancelled = true;
    };
  }, [unread]);

  return null;
}

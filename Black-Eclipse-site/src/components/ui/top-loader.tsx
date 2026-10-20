'use client';

import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { DotGrid } from '@/components/ui/ascii-loader';

// Full-page loading state for the CONTENT AREA only: during page
// transitions the sidebar stays visible while the data region goes blank
// with the grey dot-grid loader centered on top.
//
// It is deliberately INDETERMINATE. The loader cannot know how far along a
// dynamic import / data fetch is, and the old fake count-up capped at 95% and
// then sat there while a screen compiled or a request waited — reading as a
// hang ("stuck at 95%"). A plain "Loading" state is honest and never appears
// frozen at an arbitrary number. The 300ms show delay still prevents a flash on
// fast/cached loads.
export function TopLoader() {
  const [mounted, setMounted] = useState(false);
  const [left, setLeft] = useState(0);

  useEffect(() => {
    setMounted(true);
    return () => setMounted(false);
  }, []);

  // Track the sidebar's right edge so the overlay never covers the rail.
  // Polling at 120ms is cheap and follows the collapse/expand animation;
  // the loader also sits BELOW the sidebar in z-order as a safety net.
  useEffect(() => {
    if (!mounted) return;
    const measure = () => {
      const sb = document.querySelector('.sidebar-root') as HTMLElement | null;
      const right = sb ? sb.getBoundingClientRect().right : 0;
      setLeft(right > 1 ? right : 0);
    };
    measure();
    const id = setInterval(measure, 120);
    window.addEventListener('resize', measure);
    return () => {
      clearInterval(id);
      window.removeEventListener('resize', measure);
    };
  }, [mounted]);

  // Show-delay: fast fetches (<300ms) never flash the full-screen loader —
  // kills the loader flicker on quick tab switches / cached loads.
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    if (!mounted) return;
    const t = setTimeout(() => setVisible(true), 300);
    return () => clearTimeout(t);
  }, [mounted]);

  if (!mounted || !visible) return null;

  return createPortal(
    <div
      className="fixed top-0 bottom-0 right-0 z-[45] flex flex-col items-center justify-center gap-5 bg-background animate-fade-in"
      style={{ left }}
      role="status"
      aria-label="Loading"
    >
      <DotGrid size={40} />
      <span className="font-mono text-[11px] font-bold uppercase tracking-widest text-muted-foreground">
        Loading
      </span>
    </div>,
    document.body
  );
}

'use client';

import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { DotGrid } from '@/components/ui/ascii-loader';

// Full-page loading state for the CONTENT AREA only: during page
// transitions the sidebar stays visible while the data region goes blank
// with the grey dot-grid loader centered on top, plus a live progress
// number. The overlay's left edge tracks the sidebar's right edge (the
// desktop rail; on mobile it is display:none so the overlay is full-width).
export function TopLoader() {
  const [mounted, setMounted] = useState(false);
  const [pct, setPct] = useState(4);
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

  // Count-up: creeps toward 95% while work runs; the parent unmounts this
  // component when loading finishes, so 100% is never faked here.
  useEffect(() => {
    if (!mounted) return;
    const id = setInterval(() => {
      setPct(prev => Math.min(95, prev + Math.max(0.8, (95 - prev) * 0.06)));
    }, 250);
    return () => clearInterval(id);
  }, [mounted]);

  if (!mounted) return null;

  return createPortal(
    <div
      className="fixed top-0 bottom-0 right-0 z-[45] flex flex-col items-center justify-center gap-5 bg-background animate-fade-in"
      style={{ left }}
      role="status"
      aria-label={`Loading ${Math.floor(pct)}%`}
    >
      <DotGrid size={40} />
      <span className="font-mono text-[11px] font-bold text-muted-foreground tabular-nums">
        {Math.floor(pct)}%
      </span>
    </div>,
    document.body
  );
}
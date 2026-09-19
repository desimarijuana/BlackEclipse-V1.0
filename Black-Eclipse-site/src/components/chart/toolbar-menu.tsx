'use client';

// ── ToolbarMenu — portal-based frosted dropdown for the chart toolbar ─────────
// The chart toolbar uses `backdrop-filter` (glass-card-subtle), which creates a
// backdrop root: a nested dropdown's own backdrop-filter would only sample the
// toolbar's already-painted background, so it never looks truly frosted. We
// portal the menu to <body> instead, where its blur samples the whole page —
// and it also escapes the toolbar's stacking context / any overflow clipping.

import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';

interface ToolbarMenuProps {
  label: React.ReactNode;
  icon?: React.ReactNode;
  active?: boolean;
  title?: string;
  width?: number;
  align?: 'left' | 'right';
  triggerClassName?: string;
  /** Render the menu body. Call `close` to dismiss the menu. */
  children: (close: () => void) => React.ReactNode;
}

export function ToolbarMenu({
  label, icon, active, title, width = 256, align = 'left', triggerClassName, children,
}: ToolbarMenuProps) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left?: number; right?: number } | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const close = () => setOpen(false);

  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      const el = triggerRef.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      setPos(align === 'right'
        ? { top: r.bottom + 6, right: Math.max(8, window.innerWidth - r.right) }
        : { top: r.bottom + 6, left: Math.max(8, r.left) });
    };
    place();
    window.addEventListener('resize', place);
    window.addEventListener('scroll', place, true);
    return () => {
      window.removeEventListener('resize', place);
      window.removeEventListener('scroll', place, true);
    };
  }, [open, align]);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      const t = e.target as Node;
      if (triggerRef.current?.contains(t) || menuRef.current?.contains(t)) return;
      setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        title={title}
        onClick={() => setOpen((o) => !o)}
        className={cn(
          'inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[10px] font-bold transition-colors cursor-pointer',
          active ? 'bg-muted-foreground/20 text-foreground' : 'bg-accent/40 text-muted-foreground hover:text-foreground hover:bg-accent/70',
          triggerClassName,
        )}
      >
        {icon}
        {label}
        <ChevronDown size={12} className={cn('transition-transform', open && 'rotate-180')} />
      </button>
      {open && pos && typeof document !== 'undefined' && createPortal(
        <div
          ref={menuRef}
          style={{ position: 'fixed', top: pos.top, left: pos.left, right: pos.right, width }}
          className="z-[100] rounded-xl border border-border/40 glass-card-strong p-1.5 shadow-2xl animate-fade-in"
        >
          {children(close)}
        </div>,
        document.body,
      )}
    </>
  );
}

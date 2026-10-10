'use client';

// ── Investor Eye — full event dossier overlay ────────────────────────────────
// The wide, readable view of one event. The right rail is a PEEK; this is the
// full read: the same `EventPanel` in `wide` mode (sections packed into two
// columns), centred over the map so context is not lost.
//
// Portaled to `document.body` for the same containing-block reason as
// `FullPageMap` (a transformed/animated ancestor scopes the frosted glass and
// traps `position: fixed`).

import { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { ArrowLeft, X } from '@/lib/icons';
import { useInvestorEyeStore } from '@/lib/investor-eye/store';
import { EventPanel } from './event-panel';

export function EventDossierOverlay() {
  const selectedEvent = useInvestorEyeStore((s) => s.selectedEvent);
  const setSelectedEvent = useInvestorEyeStore((s) => s.setSelectedEvent);
  const setSelectedCountry = useInvestorEyeStore((s) => s.setSelectedCountry);
  const setDossierOpen = useInvestorEyeStore((s) => s.setDossierOpen);

  const close = () => setDossierOpen(false);

  // Esc closes; lock page scroll while open (mirrors FullPageMap).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') close(); };
    window.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = prev;
    };
  }, []);

  if (typeof document === 'undefined' || !selectedEvent) return null;

  return createPortal(
    <div className="fixed inset-0 z-[95] flex items-center justify-center">
      {/* Backdrop — click to return to the map. */}
      <button
        aria-label="Close dossier"
        onClick={close}
        className="absolute inset-0 bg-black/60 backdrop-blur-sm cursor-pointer"
      />

      <div className="relative z-10 flex h-[90vh] w-[94vw] max-w-6xl flex-col overflow-hidden rounded-2xl border border-white/10 glass-card">
        <div className="flex items-center justify-between gap-2 border-b border-white/10 px-3 py-2">
          <button
            onClick={close}
            className="flex items-center gap-1.5 rounded-lg px-2 py-1 text-[10px] font-semibold text-muted-foreground hover:bg-accent hover:text-foreground cursor-pointer"
            title="Back to map (Esc)"
          >
            <ArrowLeft size={12} /> Back to map
            <kbd className="ml-0.5 rounded bg-white/[0.06] px-1 py-0.5 font-mono text-[9px]">Esc</kbd>
          </button>
          <span className="truncate text-[9px] font-mono uppercase tracking-widest text-muted-foreground/70">
            Event dossier
          </span>
          <button
            onClick={close}
            className="rounded-lg p-1 text-muted-foreground hover:bg-accent hover:text-foreground cursor-pointer"
            aria-label="Close dossier"
          >
            <X size={14} />
          </button>
        </div>

        <div className="min-h-0 flex-1">
          <EventPanel
            event={selectedEvent}
            wide
            onClose={close}
            onSelectCountry={(iso2) => {
              // Pivot to the country: close the dossier and show the country panel.
              close();
              setSelectedEvent(null);
              setSelectedCountry(iso2);
            }}
          />
        </div>
      </div>
    </div>,
    document.body,
  );
}

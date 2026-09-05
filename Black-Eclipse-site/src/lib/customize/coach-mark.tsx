'use client';

// ── CustomizeCoachMark — one-time hint pointing at a page's Customize button ─
// Shows once per page (persisted in localStorage), then never again. Rendered
// absolutely inside a `relative` toolbar; anchored to the right edge so the
// arrow lands on the button. Dismissing records `eclipse_customize_hint.<pageId>`.

import { useEffect, useState } from 'react';
import { Settings2, X } from 'lucide-react';

export function CustomizeCoachMark({
  pageId,
  title = 'Make this page yours',
  body = 'Every card on this page can be rearranged, resized, shown or hidden — press Customize to arrange your workspace.',
}: {
  pageId: string;
  title?: string;
  body?: string;
}) {
  const [show, setShow] = useState(false);
  useEffect(() => {
    try { setShow(!window.localStorage.getItem(`eclipse_customize_hint.${pageId}`)); } catch { /* private mode */ }
  }, [pageId]);
  if (!show) return null;
  const dismiss = () => {
    setShow(false);
    try { window.localStorage.setItem(`eclipse_customize_hint.${pageId}`, '1'); } catch { /* private mode */ }
  };
  return (
    <div
      className="absolute right-0 top-[calc(100%+6px)] z-40 w-72 rounded-xl border border-primary/30 bg-[#101010]/95 dark:bg-[#101010]/95 backdrop-blur-md shadow-xl shadow-black/40 px-3.5 py-3 animate-fade-in-up"
      role="note"
      aria-label={title}
    >
      {/* Arrow pointing up at the Customize button */}
      <span className="absolute -top-1.5 right-6 w-3 h-3 rotate-45 rounded-[2px] bg-[#101010] border-l border-t border-primary/30" aria-hidden />
      <button
        onClick={dismiss}
        className="absolute top-2 right-2 text-muted-foreground hover:text-foreground cursor-pointer p-0.5"
        title="Got it"
      >
        <X className="w-3.5 h-3.5" />
      </button>
      <p className="text-[11px] font-bold text-primary flex items-center gap-1.5 pr-5">
        <Settings2 className="w-3.5 h-3.5 shrink-0" /> {title}
      </p>
      <p className="text-[10.5px] text-zinc-300 leading-relaxed mt-1.5">{body}</p>
      <p className="text-[9.5px] font-bold uppercase tracking-wider text-muted-foreground/70 mt-2 cursor-pointer hover:text-foreground transition-colors w-fit" onClick={dismiss}>
        Got it — don&apos;t show again
      </p>
    </div>
  );
}
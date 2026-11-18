'use client';

// ── Saved pages in the main navigation ───────────────────────────────────────
// Pages created by the user or the agent are real destinations. They render in
// the SAME nav list as the fixed tabs (no separate "SDK pages" section), and
// open through the shell's existing deep link (`?tab=pages&page=<id>`), so
// Ctrl/Cmd-click and browser back/forward keep working.

import { useCallback, useEffect, useState } from 'react';
import { FileText } from '@/lib/icons';
import { destinationToHref } from '@/lib/search/deep-link';
import { eclipseSdk } from '@/lib/sdk';
import { isSetupOverlayOpen, subscribeSetupOverlay } from '@/lib/setup/overlay';
import { isDashboardMirrorPath } from '@/lib/ui-engineering/live-page';
import { cn } from '@/lib/utils';

interface SavedPageLink {
  id: string;
  title: string;
  path?: string | null;
}

function pageFromLocation(): string | null {
  if (typeof window === 'undefined') return null;
  const sp = new URLSearchParams(window.location.search);
  return sp.get('tab') === 'pages' ? sp.get('page') : null;
}

export function SavedPagesNav({
  collapsed = false,
  active = false,
  onNavigate,
}: {
  collapsed?: boolean;
  active?: boolean;
  onNavigate?: () => void;
}) {
  const [pages, setPages] = useState<SavedPageLink[]>([]);
  const [openPageId, setOpenPageId] = useState<string | null>(pageFromLocation);

  const refresh = useCallback(async () => {
    try {
      const { blueprints } = await eclipseSdk.pages.list();
      // Dashboard mirrors are agent-readable board snapshots, not user pages.
      setPages(blueprints.filter((page) => !isDashboardMirrorPath(page.path)).slice(0, 24));
    } catch {
      /* runtime unavailable — keep the fixed nav usable */
    }
  }, []);

  useEffect(() => {
    void refresh();
    window.addEventListener('focus', refresh);
    const timer = window.setInterval(() => {
      if (!document.hidden && !isSetupOverlayOpen()) void refresh();
    }, 60_000);
    const onPop = () => setOpenPageId(pageFromLocation());
    window.addEventListener('popstate', onPop);
    // The runtime pushes `changed` when any blueprint revision moves (including
    // a page the agent just created), so the nav updates without a reload.
    // While the setup wizard is overlaid it would hold one of the browser's six
    // per-origin connections, so the stream is closed until the wizard leaves.
    let source: EventSource | null = null;
    const connect = () => {
      if (source || isSetupOverlayOpen()) return;
      try {
        source = new EventSource('/api/ui/stream');
        source.addEventListener('changed', () => void refresh());
      } catch {
        source = null; // SSE unavailable — focus/poll still refresh the list
      }
    };
    const disconnect = () => {
      source?.close();
      source = null;
    };
    connect();
    const unsubscribeOverlay = subscribeSetupOverlay((open) => {
      if (open) disconnect();
      else connect();
    });
    return () => {
      window.removeEventListener('focus', refresh);
      window.removeEventListener('popstate', onPop);
      window.clearInterval(timer);
      unsubscribeOverlay();
      disconnect();
    };
  }, [refresh]);

  if (pages.length === 0) return null;

  return (
    <>
      {pages.map((page) => {
        const selected = active && openPageId === page.id;
        const href = destinationToHref({ tab: 'pages', params: { page: page.id } });
        return (
          <a
            key={page.id}
            href={href}
            data-sound="tick"
            aria-current={selected ? 'page' : undefined}
            title={collapsed ? page.path || page.title : undefined}
            onClick={(event) => {
              if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return;
              event.preventDefault();
              setOpenPageId(page.id);
              eclipseSdk.pages.open(page.id);
              onNavigate?.();
            }}
            className={cn(
              'h-8 flex items-center px-3 py-1.5 text-xs font-semibold transition-colors cursor-pointer overflow-hidden no-underline outline-none focus-visible:ring-1 focus-visible:ring-primary/50',
              selected
                ? 'rounded-lg bg-white/[0.07] text-foreground'
                : 'rounded-lg bg-transparent text-muted-foreground hover:bg-white/[0.04] hover:text-foreground',
              collapsed ? 'justify-center w-9 px-0 gap-0' : 'justify-start w-full gap-2.5',
            )}
          >
            <span className="shrink-0 flex items-center justify-center">
              <FileText size={15} className={cn('transition-colors duration-300', selected && 'text-primary')} />
            </span>
            <span
              className={cn(
                'shrink-0 whitespace-nowrap transition-all duration-300 overflow-hidden flex-1 text-left',
                collapsed ? 'opacity-0 -translate-x-2 w-0' : 'opacity-100 translate-x-0 w-auto',
              )}
            >
              {page.title}
            </span>
          </a>
        );
      })}
    </>
  );
}

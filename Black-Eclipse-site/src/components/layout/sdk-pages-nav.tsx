'use client';

// ── SDK pages in the sidebar ─────────────────────────────────────────────────
// Saved SDK/blueprint pages are real destinations, not a hidden list inside the
// Pages tab. This panel lists them in the app navigation and opens one through
// the shell's existing deep-link path (`?tab=pages&page=<id>`), so Ctrl/Cmd-click
// and browser back/forward keep working. Fire-and-forget: a runtime that is not
// up simply renders nothing.

import { useCallback, useEffect, useState } from 'react';
import { FileText, Plus } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { eclipseSdk } from '@/lib/sdk';

interface SdkPageLink {
  id: string;
  title: string;
  path?: string | null;
}

export function SdkPagesNav({ collapsed = false }: { collapsed?: boolean }) {
  const [pages, setPages] = useState<SdkPageLink[]>([]);

  const refresh = useCallback(async () => {
    try {
      const { blueprints } = await eclipseSdk.pages.list();
      setPages(blueprints.slice(0, 12));
    } catch {
      /* runtime unavailable */
    }
  }, []);

  useEffect(() => {
    // Expose the same typed client in the browser console for scripted testing:
    // `eclipseSdk.widgets.create({...})`, `eclipseSdk.locks.create({...})`, etc.
    (window as Window & { eclipseSdk?: typeof eclipseSdk }).eclipseSdk = eclipseSdk;
    void refresh();
    window.addEventListener('focus', refresh);
    const timer = window.setInterval(refresh, 60_000);
    return () => {
      window.removeEventListener('focus', refresh);
      window.clearInterval(timer);
    };
  }, [refresh]);

  const openPagesTab = () => {
    window.history.pushState(null, '', '/?tab=pages');
    window.dispatchEvent(new PopStateEvent('popstate'));
  };

  if (pages.length === 0) return null;

  return (
    <div className="mt-3 w-full border-t border-border/10 pt-3">
      <div className={cn('mb-1.5 flex items-center justify-between px-3', collapsed && 'justify-center px-0')}>
        {!collapsed && (
          <span className="text-[9px] font-mono font-bold uppercase tracking-widest text-muted-foreground/70">
            SDK pages
          </span>
        )}
        <button
          type="button"
          onClick={openPagesTab}
          title="Manage SDK pages"
          className="rounded p-1 text-muted-foreground hover:bg-white/[0.05] hover:text-foreground"
        >
          <Plus size={12} />
        </button>
      </div>
      <div className="flex flex-col gap-0.5">
        {pages.map((page) => (
          <button
            key={page.id}
            type="button"
            onClick={() => eclipseSdk.pages.open(page.id)}
            title={page.path || page.title}
            className={cn(
              'flex items-center gap-2 rounded-lg px-3 py-1.5 text-left text-[11px] text-muted-foreground transition-colors hover:bg-white/[0.04] hover:text-foreground',
              collapsed && 'w-9 justify-center px-0',
            )}
          >
            <FileText size={12} className="shrink-0 text-primary/70" />
            {!collapsed && <span className="truncate">{page.title}</span>}
          </button>
        ))}
      </div>
    </div>
  );
}

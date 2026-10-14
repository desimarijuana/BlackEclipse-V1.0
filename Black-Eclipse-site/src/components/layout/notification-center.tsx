'use client';

// ── Notification bell + center panel ─────────────────────────────────────────
// Lives in the top bar. The bell shows the aggregate unread count; clicking it
// opens a frosted-glass panel listing the most recent entries from the
// notification ledger (`lib/notifications/store`). Clicking an entry marks its
// tab read and navigates there through the same `be:navigate` channel the
// workspace panels use; each entry can be dismissed individually, and
// "Mark all read" clears every badge. Opening the panel never marks anything
// read by itself — badges clear on navigation or explicit action only.

import { useEffect, useState } from 'react';
import { Bell, CheckCircle2, ShieldAlert, Bot, Ghost, type LucideIcon } from '@/lib/icons';
import { cn } from '@/lib/utils';
import {
  totalUnread,
  useNotificationsStore,
  type AppNotification,
  type NotificationKind,
} from '@/lib/notifications/store';

/** How many entries the panel lists (the ledger keeps 100). */
const MAX_VISIBLE = 12;

const KIND_ICON: Record<NotificationKind, LucideIcon> = {
  alert: Bell,
  task: CheckCircle2,
  approval: ShieldAlert,
  agent: Bot,
  bot: Ghost,
};

function timeAgo(at: number): string {
  const s = Math.max(0, Math.floor((Date.now() - at) / 1000));
  if (s < 60) return 'now';
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  return `${Math.floor(h / 24)}d`;
}

export function NotificationBell() {
  const items = useNotificationsStore((s) => s.items);
  const markAllRead = useNotificationsStore((s) => s.markAllRead);
  const markTabRead = useNotificationsStore((s) => s.markTabRead);
  const remove = useNotificationsStore((s) => s.remove);
  const [open, setOpen] = useState(false);
  const unread = totalUnread(items);

  // Escape closes the panel (click-outside is handled by the backdrop).
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  const openItem = (item: AppNotification) => {
    markTabRead(item.tab);
    setOpen(false);
    window.dispatchEvent(new CustomEvent('be:navigate', { detail: { tab: item.tab } }));
  };

  const visible = items.slice(0, MAX_VISIBLE);

  return (
    <div className="relative shrink-0">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-label="Notifications"
        aria-expanded={open}
        title="Notifications"
        className={cn(
          'relative flex h-10 w-10 shrink-0 items-center justify-center rounded-xl transition-colors cursor-pointer',
          open
            ? 'bg-white/[0.08] text-primary'
            : 'text-muted-foreground/70 hover:bg-accent hover:text-foreground',
        )}
      >
        <Bell size={18} />
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-rose-500 px-1 text-[9px] font-bold leading-none text-white">
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>

      {open && (
        <>
          {/* Click-outside backdrop */}
          <div className="fixed inset-0 z-[105]" onClick={() => setOpen(false)} aria-hidden="true" />
          <div
            role="dialog"
            aria-label="Notifications"
            className="absolute right-0 top-12 z-[110] flex max-h-[min(70vh,480px)] w-80 max-w-[calc(100vw-1.5rem)] flex-col overflow-hidden rounded-2xl border border-border/30 glass-card-strong shadow-lg"
          >
            <div className="flex items-center justify-between gap-2 border-b border-border/20 px-3.5 py-2.5">
              <span className="text-xs font-semibold text-foreground">Notifications</span>
              <button
                type="button"
                onClick={markAllRead}
                disabled={unread === 0}
                className="text-[10px] font-semibold text-muted-foreground hover:text-foreground disabled:opacity-40 cursor-pointer disabled:cursor-default"
              >
                Mark all read
              </button>
            </div>

            {visible.length === 0 ? (
              <p className="px-3.5 py-6 text-center text-xs text-muted-foreground">
                Nothing yet — alerts, finished tasks and bot runs land here.
              </p>
            ) : (
              <ul className="flex-1 overflow-y-auto py-1">
                {visible.map((item) => {
                  const Icon = KIND_ICON[item.kind] ?? Bell;
                  return (
                    <li key={item.id} className="group flex items-stretch gap-0.5 px-1">
                      <button
                        type="button"
                        onClick={() => openItem(item)}
                        className="flex min-w-0 flex-1 items-start gap-2.5 rounded-xl px-2.5 py-2 text-left transition-colors hover:bg-white/[0.05] cursor-pointer"
                      >
                        <span className="relative mt-0.5 shrink-0 text-muted-foreground">
                          <Icon size={14} />
                          {!item.read && (
                            <span className="absolute -right-1 -top-1 h-1.5 w-1.5 rounded-full bg-rose-500" />
                          )}
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="flex items-baseline justify-between gap-2">
                            <span className={cn('truncate text-[11px]', item.read ? 'font-medium text-muted-foreground' : 'font-semibold text-foreground')}>
                              {item.title}
                            </span>
                            <span className="shrink-0 text-[9px] text-muted-foreground/70">{timeAgo(item.at)}</span>
                          </span>
                          {item.body && (
                            <span className="mt-0.5 line-clamp-2 break-words text-[10px] leading-snug text-muted-foreground">
                              {item.body}
                            </span>
                          )}
                        </span>
                      </button>
                      <button
                        type="button"
                        onClick={() => remove(item.id)}
                        aria-label="Dismiss notification"
                        title="Dismiss"
                        className="shrink-0 self-start rounded-lg px-1.5 py-2 text-xs text-transparent transition-colors hover:text-foreground group-hover:text-muted-foreground cursor-pointer"
                      >
                        ×
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </>
      )}
    </div>
  );
}

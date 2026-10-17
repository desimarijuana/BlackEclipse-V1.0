'use client';

// ── Channel Gateway launcher ────────────────────────────────────────────────
// A compact pop-up from the sidebar that surfaces the existing Channel Gateway
// (Settings › Connections) without making the user hunt through Settings. The
// panel is lazy-loaded so the always-mounted sidebar never pays for it until the
// dialog is actually opened. The panel is self-contained (it fetches its own
// runtime state and never returns credentials), so embedding it here is pure
// reuse — there is no second connection store.

import dynamic from 'next/dynamic';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { ChatsCircle, Loader2 } from '@/lib/icons';
import { useT } from '@/lib/i18n';

const ConnectionsSettingsPanel = dynamic(
  () => import('@/components/screens/connections-settings').then((m) => m.ConnectionsSettingsPanel),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-40 items-center justify-center gap-2 text-xs text-muted-foreground">
        <Loader2 size={14} className="animate-spin" />
      </div>
    ),
  },
);

export function SidebarGatewayDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const t = useT();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[min(85dvh,800px)] w-[calc(100vw-2rem)] max-w-none flex-col gap-0 overflow-hidden rounded-2xl border border-white/10 glass-card-strong p-0 text-foreground sm:max-w-6xl">
        <DialogHeader className="shrink-0 border-b border-border/10 px-5 py-3.5">
          <DialogTitle className="flex items-center gap-2 text-sm font-semibold">
            <ChatsCircle size={15} className="text-muted-foreground" />
            {t('sidebar.gateway')}
          </DialogTitle>
          <DialogDescription className="text-[11px] text-muted-foreground">
            {t('sidebar.gatewayDialogHint')}
          </DialogDescription>
        </DialogHeader>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          <ConnectionsSettingsPanel />
        </div>
      </DialogContent>
    </Dialog>
  );
}

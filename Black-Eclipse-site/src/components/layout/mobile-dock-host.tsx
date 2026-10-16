'use client';

// ── MobileDockHost — the Agent Workspace / scheduler as a phone bottom sheet ──
// On desktop these docks are real side columns (they shrink the main panel to
// make room). On phones a fixed side column is unusable, so the SAME components
// render inside a bottom sheet driven by the shared `useWorkspaceStore.open`
// flag — one open/close control for the TopBar toggle, the sidebar and here.

import { Sheet, SheetContent } from '@/components/ui/sheet';
import { useWorkspaceStore } from '@/lib/agent-workspace/store';
import { AgentWorkspace } from '@/components/agent-workspace/workspace';
import { BotSchedulerDock } from '@/components/bots/scheduler-dock';
import type { AppTab } from '@/lib/app-tabs';

export function MobileDockHost({ activeTab }: { activeTab: AppTab }) {
  const open = useWorkspaceStore((s) => s.open);
  const setOpen = useWorkspaceStore((s) => s.setOpen);

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetContent
        side="bottom"
        showCloseButton={false}
        className="h-[85dvh] rounded-t-2xl p-0 overflow-hidden"
      >
        {/* Give the dock a definite height so its inner scroll region resolves. */}
        <div className="flex h-full min-h-0 flex-col [&>div]:h-full [&>div]:min-h-0">
          {activeTab === 'bots'
            ? <BotSchedulerDock />
            : <AgentWorkspace showExplain={activeTab === 'chat'} />}
        </div>
      </SheetContent>
    </Sheet>
  );
}

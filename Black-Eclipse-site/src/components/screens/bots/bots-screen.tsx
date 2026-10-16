'use client';

// ── Bots workspace ───────────────────────────────────────────────────────────
// The conversation IS the page: a full-height chat with a bot (or a group room).
// The bot list AND group chats live in the LEFT app sidebar (Bots mode). The
// scheduled-jobs scheduler is the right-docked Agent Workspace slot (see
// `components/bots/scheduler-dock.tsx`), opened from the left sidebar. Every
// control reads and writes REAL state via `/api/automations`.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useT } from '@/lib/i18n';
import { Ghost, Plus, Users } from '@/lib/icons';
import { Button } from '@/components/ui/button';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { BotChat } from '@/components/bots/bot-chat';
import { CreateBotDialog } from '@/components/bots/create-bot-dialog';
import { GroupChatDialog } from '@/components/bots/group-chat-dialog';
import { GroupChatRoom } from '@/components/bots/group-chat-room';
import {
  createAutomation, deleteAutomation, runAutomationNow,
  type AutomationView,
} from '@/lib/harness/automation-browser';
import { useBotsStore } from '@/lib/bots/bots-store';
import { useHydrateBotAvatars } from '@/lib/bots/avatar-store';
import { useBotGroupsStore, useHydrateBotGroups } from '@/lib/bots/groups-store';

export function BotsScreen() {
  const t = useT();
  useHydrateBotAvatars();
  useHydrateBotGroups();

  const bots = useBotsStore((s) => s.bots);
  const error = useBotsStore((s) => s.error);
  const loading = useBotsStore((s) => s.loading);
  const selectedId = useBotsStore((s) => s.selectedId);
  const selectedGroupId = useBotsStore((s) => s.selectedGroupId);
  const hydrate = useBotsStore((s) => s.hydrate);
  const select = useBotsStore((s) => s.select);
  const selectGroup = useBotsStore((s) => s.selectGroup);
  const createOpen = useBotsStore((s) => s.createOpen);
  const openCreate = useBotsStore((s) => s.openCreate);
  const setCreateOpen = useBotsStore((s) => s.setCreateOpen);
  const groupCreateOpen = useBotsStore((s) => s.groupCreateOpen);
  const openGroupCreate = useBotsStore((s) => s.openGroupCreate);
  const setGroupCreateOpen = useBotsStore((s) => s.setGroupCreateOpen);

  const groups = useBotGroupsStore((s) => s.groups);
  const createGroup = useBotGroupsStore((s) => s.createGroup);

  const [busyId, setBusyId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<AutomationView | null>(null);
  const [runKey, setRunKey] = useState(0);
  const [actionError, setActionError] = useState<string | null>(null);
  const didAutoSelect = useRef(false);

  // Initial load + a slow refresh so the list stays current across tabs.
  useEffect(() => {
    void hydrate();
    const timer = setInterval(() => void hydrate(), 20000);
    return () => clearInterval(timer);
  }, [hydrate]);

  // Deep link: /?tab=bots&bot=<id> or /?tab=bots&group=<id> (read once on mount).
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const params = new URLSearchParams(window.location.search);
    const bot = params.get('bot');
    const group = params.get('group');
    if (bot) select(bot);
    else if (group) selectGroup(group);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Default the page to the most recent conversation. Runs once, after the list
  // loads, and never overrides an explicit deep link or selection.
  useEffect(() => {
    if (didAutoSelect.current || loading) return;
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search);
      if (params.get('bot') || params.get('group')) {
        didAutoSelect.current = true;
        return;
      }
    }
    if (selectedId || selectedGroupId) {
      didAutoSelect.current = true;
      return;
    }
    if (bots.length === 0) return;
    didAutoSelect.current = true;
    const recent = [...bots].sort((a, b) => recency(b) - recency(a))[0];
    select(recent.id);
  }, [bots, loading, selectedId, selectedGroupId, select]);

  const selectedBot = useMemo(() => bots.find((b) => b.id === selectedId) ?? null, [bots, selectedId]);
  const selectedGroup = useMemo(() => groups.find((g) => g.id === selectedGroupId) ?? null, [groups, selectedGroupId]);

  const runAction = useCallback(
    async (id: string, fn: () => Promise<unknown>) => {
      setBusyId(id);
      setActionError(null);
      try {
        await fn();
        await hydrate();
      } catch (err) {
        setActionError(err instanceof Error ? err.message : 'action failed');
      } finally {
        setBusyId(null);
      }
    },
    [hydrate],
  );

  const runNow = useCallback(
    (bot: AutomationView) => {
      setRunKey((k) => k + 1);
      return runAction(bot.id, () => runAutomationNow(bot.id));
    },
    [runAction],
  );

  const confirmDelete = useCallback(async () => {
    if (!deleteTarget) return;
    const id = deleteTarget.id;
    setDeleteTarget(null);
    if (selectedId === id) select(null);
    await runAction(id, () => deleteAutomation(id));
  }, [deleteTarget, selectedId, runAction, select]);

  const handleGroupCreate = useCallback(
    (input: { name: string; memberIds: string[]; image?: string }) => {
      const group = createGroup(input);
      setGroupCreateOpen(false);
      selectGroup(group.id);
    },
    [createGroup, setGroupCreateOpen, selectGroup],
  );

  const handleCreated = useCallback(
    (bot: AutomationView) => {
      setCreateOpen(false);
      void hydrate();
      select(bot.id);
    },
    [setCreateOpen, hydrate, select],
  );

  return (
    <div className="flex h-full min-h-0 w-full flex-col">
      {(actionError || error) && (
        <div className="glass-card-subtle mx-2 mt-2 flex items-center gap-2 rounded-lg border border-rose-500/30 px-3 py-2 text-sm text-rose-300 md:mx-3">
          <span className="flex-1">{actionError || error}</span>
          <button type="button" onClick={() => { setActionError(null); void hydrate(); }} className="text-xs underline">
            {t('common.reset')}
          </button>
        </div>
      )}

      {/* The conversation — full page. */}
      <div className="min-h-0 flex-1 p-2 md:p-3">
        {selectedGroup ? (
          <GroupChatRoom
            group={selectedGroup}
            bots={bots}
            onDeleted={() => selectGroup(null)}
            onChanged={() => void hydrate()}
          />
        ) : selectedBot ? (
          <BotChat
            bot={selectedBot}
            busy={busyId === selectedBot.id}
            onClose={() => select(null)}
            onChanged={() => void hydrate()}
            onRunNow={(bot) => runNow(bot)}
            refreshKey={runKey}
            onDuplicate={(bot) => runAction(bot.id, () => duplicateBot(bot))}
            onDelete={(bot) => setDeleteTarget(bot)}
          />
        ) : (
          <CenterEmpty onCreate={openCreate} onCreateGroup={openGroupCreate} />
        )}
      </div>

      {/* New bot — avatar picker + identity, opened from the header and sidebar. */}
      <CreateBotDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        existingNames={bots.map((b) => b.name)}
        onCreated={handleCreated}
      />

      {/* New group chat — pick 2–6 bots. */}
      <GroupChatDialog
        open={groupCreateOpen}
        onOpenChange={setGroupCreateOpen}
        bots={bots}
        onCreate={handleGroupCreate}
      />

      {/* Delete confirmation — destructive, with the real consequence stated. */}
      <Dialog open={Boolean(deleteTarget)} onOpenChange={(open) => { if (!open) setDeleteTarget(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('bots.delete')}</DialogTitle>
            <DialogDescription>
              {t('bots.deleteConfirm')} {deleteTarget ? `“${deleteTarget.name}”` : ''}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDeleteTarget(null)}>{t('bots.cancel')}</Button>
            <Button variant="destructive" onClick={confirmDelete}>{t('bots.delete')}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

/** Duplicate a bot's configuration as a new PAUSED draft so it can be reviewed
 *  before it ever runs. */
async function duplicateBot(bot: AutomationView): Promise<AutomationView> {
  return createAutomation({
    name: `${bot.name} copy`,
    description: bot.description ?? bot.action.objective ?? undefined,
    state: 'paused',
    trigger: {
      type: bot.trigger.type,
      cron: bot.trigger.cron,
      intervalSeconds: bot.trigger.intervalSeconds,
      runAt: bot.trigger.runAt,
      timezone: bot.trigger.timezone,
      // Carry the non-timed trigger fields too, so duplicating an event/condition
      // bot does not silently downgrade it to an event type with no target.
      eventType: bot.trigger.eventType,
      eventFilter: bot.trigger.eventFilter,
      condition: bot.trigger.condition,
      startAt: bot.trigger.startAt,
      endAt: bot.trigger.endAt,
    },
    condition: bot.condition ?? undefined,
    action: {
      type: bot.action.type,
      objective: bot.action.objective,
      agentId: bot.action.agentId,
    },
    tags: [...bot.tags.filter((x) => x !== 'bot'), 'bot'],
  });
}

function CenterEmpty({
  onCreate, onCreateGroup,
}: {
  onCreate: () => void;
  onCreateGroup: () => void;
}) {
  const t = useT();
  return (
    <div className="glass-card flex h-full min-h-[20rem] flex-col items-center justify-center rounded-2xl px-6 text-center">
      <div className="glass-card-subtle flex h-14 w-14 items-center justify-center rounded-2xl text-muted-foreground">
        <Ghost size={26} />
      </div>
      <p className="mt-4 max-w-sm text-sm text-muted-foreground">{t('bots.workspace.selectPrompt')}</p>
      <div className="mt-4 flex flex-wrap justify-center gap-2">
        <Button onClick={onCreate}>
          <Plus size={14} /> {t('bots.dialog.title')}
        </Button>
        <Button variant="outline" onClick={onCreateGroup}>
          <Users size={14} /> {t('bots.groups.new')}
        </Button>
      </div>
    </div>
  );
}

/** Recency for defaulting to the most recent conversation: the last run, else
 *  the last edit. */
function recency(bot: AutomationView): number {
  const ts = bot.lastRunAt ?? bot.updatedAt;
  return ts ? Date.parse(ts) : 0;
}

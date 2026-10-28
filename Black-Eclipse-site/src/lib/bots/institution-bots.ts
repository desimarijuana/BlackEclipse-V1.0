// -- Institution starter pack -------------------------------------------------
// Creates the six/seven committee seats as REAL automations (idempotent by name)
// plus one "Investment Committee" group room for casual chat. The pipeline itself
// is a Team run, not a group turn: `runInstitution` starts the durable task graph
// (analyst -> debate -> trader -> risk -> PM). Nothing is fabricated; every bot is
// a normal automation the operator can pause, edit or delete.

'use client';

import { useCallback, useState } from 'react';
import {
  createAutomation,
  type AutomationView,
  type CreateAutomationInput,
} from '@/lib/harness/automation-browser';
import { getInstitutionPreset } from '@/lib/harness/team-client';
import { useBotsStore } from '@/lib/bots/bots-store';
import { useBotGroupsStore } from '@/lib/bots/groups-store';
import { localTimezone } from '@/lib/bots/state';

/** The chat room that holds the committee (groups cap at 6 members). */
export const INSTITUTION_GROUP_NAME = 'Investment Committee';

/** The chair is the seventh seat; the chat room is capped at six. */
const GROUP_STAGE_ORDER = ['analyst', 'bull', 'bear', 'trader', 'risk', 'pm'];

export interface InstitutionSeedResult {
  groupId: string | null;
  created: number;
  reused: number;
}

function manualTrigger(): CreateAutomationInput['trigger'] {
  return { type: 'manual', timezone: localTimezone() };
}

/**
 * Create any missing committee bots and repair the group room. The role specs
 * come from the Python preset, so the bot identities can never drift from the
 * agents the team graph actually runs.
 */
export async function seedInstitutionPack(
  existing: AutomationView[],
): Promise<InstitutionSeedResult> {
  const { bots: specs } = await getInstitutionPreset({ objective: '' });
  const byName = new Map(existing.map((b) => [b.name.trim().toLowerCase(), b]));

  const members: AutomationView[] = [];
  let created = 0;
  let reused = 0;
  for (const spec of specs) {
    const found = byName.get(spec.name.trim().toLowerCase());
    if (found) {
      members.push(found);
      reused += 1;
      continue;
    }
    const bot = await createAutomation({
      name: spec.name,
      description: spec.description,
      state: 'active',
      trigger: manualTrigger(),
      action: {
        type: 'run_agent',
        objective: spec.objective,
        agentId: spec.agentId,
      },
      tags: spec.tags,
    });
    members.push(bot);
    created += 1;
  }

  // Group rooms cap at 6; pick the seats that make a useful chat (no chair).
  const groupMemberIds = members
    .filter((bot) => {
      const spec = specs.find((s) => s.name === bot.name);
      return spec ? GROUP_STAGE_ORDER.includes(spec.stage) : true;
    })
    .slice(0, 6)
    .map((b) => b.id);

  const groupStore = useBotGroupsStore.getState();
  const existingGroup = groupStore.groups.find(
    (g) => g.name.trim().toLowerCase() === INSTITUTION_GROUP_NAME.toLowerCase(),
  );
  if (!existingGroup) {
    if (groupMemberIds.length < 2) {
      return { groupId: null, created, reused };
    }
    const group = groupStore.createGroup({
      name: INSTITUTION_GROUP_NAME,
      memberIds: groupMemberIds,
    });
    return { groupId: group.id, created, reused };
  }
  const known = new Set([...existing.map((b) => b.id), ...groupMemberIds]);
  const merged = [
    ...new Set([...existingGroup.memberIds.filter((id) => known.has(id)), ...groupMemberIds]),
  ].slice(0, 6);
  groupStore.setMembers(existingGroup.id, merged);
  return { groupId: existingGroup.id, created, reused };
}

/** UI hook: seed the committee, refresh the bot list and open the room. */
export function useSeedInstitutionPack() {
  const hydrate = useBotsStore((s) => s.hydrate);
  const selectGroup = useBotsStore((s) => s.selectGroup);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const seed = useCallback(async () => {
    if (busy) return false;
    setBusy(true);
    setError(null);
    try {
      const { groupId } = await seedInstitutionPack(useBotsStore.getState().bots);
      await hydrate();
      if (groupId) selectGroup(groupId);
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not add the Institution bots.');
      return false;
    } finally {
      setBusy(false);
    }
  }, [busy, hydrate, selectGroup]);

  return { seed, busy, error };
}

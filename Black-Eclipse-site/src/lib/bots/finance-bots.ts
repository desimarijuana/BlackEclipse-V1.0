// ── Finance starter pack ─────────────────────────────────────────────────────
// A curated set of real, scheduled finance bots plus a single "Markets Desk"
// group room that gathers them all. The specs are pure data; `seedFinancePack`
// creates any missing bots through the REAL automation API (idempotent by name)
// and writes the group into the client-side groups store. Nothing is fabricated:
// every bot is a normal automation the user can pause, edit or delete.

'use client';

import { useCallback, useState } from 'react';
import {
  createAutomation,
  type AutomationView,
  type CreateAutomationInput,
} from '@/lib/harness/automation-browser';
import { useBotsStore } from '@/lib/bots/bots-store';
import { useBotGroupsStore } from '@/lib/bots/groups-store';
import { localTimezone } from '@/lib/bots/state';

/** The single room that holds the whole pack (group max is 6 members). */
export const FINANCE_GROUP_NAME = 'Markets Desk';

export interface FinanceBotSpec {
  name: string;
  /** Short one-line description shown under the bot name. */
  description: string;
  objective: string;
  agentId: string;
  trigger: CreateAutomationInput['trigger'];
}

const COMMON_RULES =
  'Use only retrieved data and always cite the source and as-of date/time. ' +
  'If a figure is unavailable, write UNAVAILABLE — never estimate or fabricate. ' +
  'Prefer JDdS first, then configured providers, then official web sources.';

/** The six finance bots. Recomputed per call so the schedule uses the local tz. */
export function financeBotPack(): FinanceBotSpec[] {
  const timezone = localTimezone();
  return [
    {
      name: 'Market Brief',
      description: 'Pre-open recap of the market: index moves, breadth, sectors and key macro.',
      objective:
        'Produce a concise pre-open market brief. Cover the major index levels and ' +
        'change, market breadth, the strongest and weakest sectors, and the day’s key ' +
        'macro drivers. Flag the top movers with a one-line reason each and note any ' +
        'scheduled events (earnings, policy decisions) for the session. ' + COMMON_RULES,
      agentId: 'eclipse-agent',
      trigger: { type: 'cron', cron: '0 8 * * 1-5', timezone },
    },
    {
      name: 'Watchlist Sentinel',
      description: 'Watches your list for material price moves and the news behind them.',
      objective:
        'Review the watchlist and report any material price or volume move since the ' +
        'last check. For each move, give the size and direction, the likely catalyst ' +
        'with a cited source, and whether it is news-driven or technical. Stay silent ' +
        'when nothing material changed. ' + COMMON_RULES,
      agentId: 'eclipse-agent',
      trigger: { type: 'interval', intervalSeconds: 3600, timezone },
    },
    {
      name: 'Portfolio Risk Review',
      description: 'Weekly read on concentration, drawdown and exposure.',
      objective:
        'Review the portfolio and report concentration by position and sector, current ' +
        'drawdown from peak, and overall exposure. Call out the largest risk the ' +
        'positions share and one concrete, evidence-based watch item for the week. ' +
        COMMON_RULES,
      agentId: 'eclipse-agent',
      trigger: { type: 'cron', cron: '0 17 * * 5', timezone },
    },
    {
      name: 'Earnings Radar',
      description: 'Upcoming earnings, dividends and corporate actions.',
      objective:
        'List the upcoming earnings, dividend and corporate-action dates relevant to ' +
        'the user’s holdings and watchlist. For each, state the expected date, what is ' +
        'expected and the source; mark uncertain dates as UNAVAILABLE rather than ' +
        'guessing. ' + COMMON_RULES,
      agentId: 'eclipse-agent',
      trigger: { type: 'cron', cron: '30 7 * * 1-5', timezone },
    },
    {
      name: 'Macro Pulse',
      description: 'Policy rate, currency, rates and commodities at a glance.',
      objective:
        'Summarize the macro backdrop: central-bank policy rate and last decision, the ' +
        'local currency level versus the dollar, short-term rates, and key commodities ' +
        '(gold, crude). Give the latest value, the change, and the source for each. ' +
        COMMON_RULES,
      agentId: 'eclipse-agent',
      trigger: { type: 'cron', cron: '0 9 * * *', timezone },
    },
    {
      name: 'Data Quality Auditor',
      description: 'Flags stale or missing market data before it misleads anyone.',
      objective:
        'Audit the market data the app relies on and report any gaps: stale prices, ' +
        'missing sessions, or series that failed to update. For each issue, name the ' +
        'series, how stale it is, and the likely cause where known. If everything is ' +
        'fresh, say so plainly. ' + COMMON_RULES,
      agentId: 'eclipse-agent',
      trigger: { type: 'cron', cron: '0 6 * * *', timezone },
    },
  ];
}

export interface SeedResult {
  groupId: string | null;
  created: number;
  reused: number;
}

/**
 * Create any missing pack bots (matched by name, so re-running never duplicates)
 * and ensure the group room exists with them as members. Returns the group id.
 */
export async function seedFinancePack(existing: AutomationView[]): Promise<SeedResult> {
  const pack = financeBotPack();
  const byName = new Map(existing.map((b) => [b.name.trim().toLowerCase(), b]));

  const members: AutomationView[] = [];
  let created = 0;
  let reused = 0;
  for (const spec of pack) {
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
      trigger: spec.trigger,
      action: { type: 'run_agent', objective: spec.objective, agentId: spec.agentId },
      tags: ['bot', 'finance'],
    });
    members.push(bot);
    created += 1;
  }

  const groupStore = useBotGroupsStore.getState();
  const memberIds = members.slice(0, 6).map((b) => b.id);
  const existingGroup = groupStore.groups.find(
    (g) => g.name.trim().toLowerCase() === FINANCE_GROUP_NAME.toLowerCase(),
  );
  const group = existingGroup ?? groupStore.createGroup({ name: FINANCE_GROUP_NAME, memberIds });
  return { groupId: group.id, created, reused };
}

/** UI hook: seed the pack, refresh the bot list and open the group room. */
export function useSeedFinancePack() {
  const hydrate = useBotsStore((s) => s.hydrate);
  const selectGroup = useBotsStore((s) => s.selectGroup);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const seed = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const { groupId } = await seedFinancePack(useBotsStore.getState().bots);
      await hydrate();
      if (groupId) selectGroup(groupId);
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not add the finance bots.');
      return false;
    } finally {
      setBusy(false);
    }
  }, [busy, hydrate, selectGroup]);

  return { seed, busy, error };
}

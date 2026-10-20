// Duplicate a bot's configuration as a new PAUSED draft so it can be reviewed
// before it ever runs. Shared by the Bots workspace header and the sidebar's
// per-bot menu.

import {
  createAutomation,
  type AutomationView,
} from '@/lib/harness/automation-browser';

export async function duplicateBot(bot: AutomationView): Promise<AutomationView> {
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

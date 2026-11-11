import { describe, expect, it } from 'vitest';
import type { AutomationView } from '@/lib/harness/automation-client';
import {
  BOT_FILTERS,
  botMatchesFilter,
  botMatchesSearch,
  botModelPin,
  buildModelConfig,
  buildPolicies,
  buildTrigger,
  cronSummary,
  detectSchedule,
  draftFromBot,
  intervalSecondsOf,
  emptyBotDraft,
  executionLabel,
  executionTone,
  formatDuration,
  formatRelative,
  isLiveExecution,
  isTerminalExecution,
  isBotAutomation,
  needsAttention,
  scheduleSummary,
  summarizeDraft,
  validateDraft,
} from './state';

function bot(overrides: Partial<AutomationView> = {}): AutomationView {
  const base = {
    id: 'b1',
    name: 'Watchlist watcher',
    description: 'Reviews my watchlist each morning',
    version: 1,
    state: 'active',
    trigger: {
      type: 'cron', cron: '0 8 * * 1-5', intervalSeconds: null, runAt: null,
      eventType: null, eventFilter: {}, condition: null, timezone: 'UTC',
      startAt: null, endAt: null,
    },
    condition: null,
    action: {
      type: 'run_agent', objective: 'Review the watchlist and cite sources',
      agentId: 'eclipse-agent', workflowId: null, workflowInput: {}, toolName: null,
      toolArgs: {}, taskTitle: null, skillId: null, skillVersion: null,
      workspaceRoot: null, autonomy: null, notificationTemplate: null,
      credentialRef: null, config: {},
    },
    execution: { maxRuntimeS: 900, misfire: 'skip', catchUpMax: 1, timeoutS: null },
    retry: { maxAttempts: 1, initialBackoffS: 5, backoffMultiplier: 2, maxBackoffS: 300, jitter: true, retryableClasses: [], nonRetryableClasses: [] },
    concurrency: { maxConcurrentRuns: 1, onConflict: 'skip_if_running' },
    limits: { maxRuntimeS: null, maxTokens: null, maxCost: null, maxToolCalls: null, maxParallelTasks: null, maxRetries: null },
    permissions: { allowed: [], denied: [], requiresApproval: false, approvalScope: null },
    delivery: { onSuccess: true, onFailure: true, onApprovalRequired: true, onConditionTriggered: true, onTimeout: true, adapter: 'in_app', title: null, destination: null, targets: [] },
    scopeId: null,
    tags: ['bot'],
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
    lastRunAt: null,
    nextRunAt: '2026-02-01T08:00:00Z',
    consecutiveFailures: 0,
    breaker: 'closed',
    breakerOpenedAt: null,
    breakerResetBy: null,
  } as AutomationView;
  return { ...base, ...overrides };
}

describe('execution states', () => {
  it('classifies terminal vs live states', () => {
    for (const s of ['completed', 'failed', 'cancelled', 'timed_out', 'skipped', 'blocked'] as const) {
      expect(isTerminalExecution(s)).toBe(true);
      expect(isLiveExecution(s)).toBe(false);
    }
    for (const s of ['triggered', 'queued', 'running', 'waiting', 'retrying'] as const) {
      expect(isLiveExecution(s)).toBe(true);
      expect(isTerminalExecution(s)).toBe(false);
    }
  });

  it('maps tones and labels for every represented state', () => {
    expect(executionTone('completed')).toBe('positive');
    expect(executionTone('failed')).toBe('danger');
    expect(executionTone('running')).toBe('info');
    expect(executionLabel('waiting')).toMatch(/approval/i);
  });
});

describe('filters', () => {
  it('exposes exactly the supported filters', () => {
    expect(BOT_FILTERS.map((f) => f.id)).toEqual(['all', 'active', 'paused', 'running', 'attention']);
  });

  it('matches by lifecycle, live runs and attention', () => {
    const active = bot({ state: 'active' });
    const paused = bot({ state: 'paused' });
    const attention = bot({ breaker: 'open' });
    const failing = bot({ consecutiveFailures: 2 });

    expect(botMatchesFilter(active, 'all', new Set())).toBe(true);
    expect(botMatchesFilter(active, 'active', new Set())).toBe(true);
    expect(botMatchesFilter(paused, 'active', new Set())).toBe(false);
    expect(botMatchesFilter(active, 'paused', new Set())).toBe(false);
    expect(botMatchesFilter(active, 'running', new Set(['b1']))).toBe(true);
    expect(botMatchesFilter(active, 'running', new Set())).toBe(false);
    expect(needsAttention(attention)).toBe(true);
    expect(needsAttention(failing)).toBe(true);
    expect(needsAttention(active)).toBe(false);
  });

  it('searches name, description, objective and tags', () => {
    const b = bot();
    expect(botMatchesSearch(b, 'watchlist')).toBe(true);
    expect(botMatchesSearch(b, 'CITE')).toBe(true);
    expect(botMatchesSearch(b, 'nope')).toBe(false);
    expect(botMatchesSearch(b, '  ')).toBe(true);
  });
});

describe('schedule summary', () => {
  it('summarizes common cron shapes without leaking raw cron', () => {
    expect(cronSummary('0 8 * * *')).toBe('Every day at 08:00');
    expect(cronSummary('30 9 * * 1-5')).toBe('Every weekday at 09:30');
    expect(cronSummary('0 8 * * 1')).toBe('Every Monday at 08:00');
  });

  it('summarizes interval / once / manual / event triggers', () => {
    expect(scheduleSummary({ ...bot().trigger, type: 'interval', intervalSeconds: 3600 })).toBe('Every 1 hour');
    expect(scheduleSummary({ ...bot().trigger, type: 'interval', intervalSeconds: 90000 })).toBe('Every 25 hours');
    expect(scheduleSummary({ ...bot().trigger, type: 'manual' })).toMatch(/on demand/i);
    expect(scheduleSummary({ ...bot().trigger, type: 'event', eventType: 'filing.created' })).toBe('When filing.created occurs');
  });
});

describe('draft validation and trigger building', () => {
  it('flags missing name/objective', () => {
    const issues = validateDraft(emptyBotDraft());
    expect(issues.map((i) => i.field)).toContain('name');
    expect(issues.map((i) => i.field)).toContain('objective');
  });

  it('builds cron triggers for daily/weekdays/weekly', () => {
    const base = { ...emptyBotDraft(), name: 'b', objective: 'o', time: '09:30' };
    expect(buildTrigger({ ...base, schedule: 'daily' })).toMatchObject({ type: 'cron', cron: '30 9 * * *' });
    expect(buildTrigger({ ...base, schedule: 'weekdays' })).toMatchObject({ type: 'cron', cron: '30 9 * * 1-5' });
    expect(buildTrigger({ ...base, schedule: 'weekly', weekday: 3 })).toMatchObject({ type: 'cron', cron: '30 9 * * 3' });
  });

  it('builds interval triggers in seconds/minutes and clamps to the 30s floor', () => {
    const base = { ...emptyBotDraft(), schedule: 'interval' as const };
    expect(buildTrigger({ ...base, intervalValue: 1, intervalUnit: 'minutes' }))
      .toMatchObject({ type: 'interval', intervalSeconds: 60 });
    expect(buildTrigger({ ...base, intervalValue: 30, intervalUnit: 'seconds' }))
      .toMatchObject({ type: 'interval', intervalSeconds: 30 });
    expect(buildTrigger({ ...base, intervalValue: 5, intervalUnit: 'seconds' }))
      .toMatchObject({ type: 'interval', intervalSeconds: 30 });
  });

  it('round-trips a 30s interval bot back into a draft', () => {
    const b = bot({ trigger: { ...bot().trigger, type: 'interval', intervalSeconds: 30 } });
    const draft = draftFromBot(b);
    expect(draft.schedule).toBe('interval');
    expect(draft.intervalUnit).toBe('seconds');
    expect(draft.intervalValue).toBe(30);
    expect(buildTrigger(draft)).toMatchObject({ type: 'interval', intervalSeconds: 30 });
  });

  it('summarizes sub-minute intervals in seconds', () => {
    expect(scheduleSummary({ ...bot().trigger, type: 'interval', intervalSeconds: 30 })).toBe('Every 30 seconds');
    expect(scheduleSummary({ ...bot().trigger, type: 'interval', intervalSeconds: 60 })).toBe('Every 1 minute');
  });

  it('summarizes a draft for the review step', () => {
    const draft = { ...emptyBotDraft(), name: 'b', objective: 'o', schedule: 'weekdays' as const, time: '08:00' };
    expect(summarizeDraft(draft)).toBe('Every weekday at 08:00');
  });

  it('round-trips a weekly cron bot back into a draft', () => {
    const b = bot({ trigger: { ...bot().trigger, type: 'cron', cron: '30 9 * * 3' } });
    const draft = draftFromBot(b);
    expect(draft.schedule).toBe('weekly');
    expect(draft.weekday).toBe(3);
    expect(draft.time).toBe('09:30');
  });
});

describe('description schedule detection', () => {
  it('reads a numbered interval from the description', () => {
    expect(detectSchedule('check my portfolio every 5 minutes')?.patch)
      .toMatchObject({ schedule: 'interval', intervalValue: 5, intervalUnit: 'minutes' });
    expect(detectSchedule('watch the market every 2 hours')?.patch)
      .toMatchObject({ schedule: 'interval', intervalValue: 2, intervalUnit: 'hours' });
  });

  it('reads daily/weekday/weekly cadences, with a time when given', () => {
    expect(detectSchedule('summarize news daily')?.patch).toMatchObject({ schedule: 'daily' });
    expect(detectSchedule('review positions every week at 9am')?.patch)
      .toMatchObject({ schedule: 'weekly', time: '09:00' });
    expect(detectSchedule('run a report every weekday at 8:30')?.patch)
      .toMatchObject({ schedule: 'weekdays', time: '08:30' });
    expect(detectSchedule('email me each Monday at 5pm')?.patch)
      .toMatchObject({ schedule: 'weekly', weekday: 1, time: '17:00' });
  });

  it('applies a detected schedule as a real trigger', () => {
    const det = detectSchedule('check risk every 30 minutes');
    expect(det).not.toBeNull();
    if (!det) return;
    const trigger = buildTrigger({ ...emptyBotDraft(), ...det.patch });
    expect(trigger).toMatchObject({ type: 'interval', intervalSeconds: 1800 });
  });

  it('reads a monthly day ("on the 15th") rather than defaulting to the 1st', () => {
    const det = detectSchedule('email me a report monthly on the 15th at 6pm');
    expect(det?.patch).toMatchObject({ schedule: 'monthly', dom: 15, time: '18:00' });
  });

  it('stays manual when there is no schedule phrase', () => {
    expect(detectSchedule('answer questions about my holdings')).toBeNull();
    expect(detectSchedule('')).toBeNull();
  });
});

describe('schedule summary edge cases', () => {
  it('summarizes sub-daily crons instead of mislabelling them "Every day"', () => {
    expect(cronSummary('* * * * *')).toBe('Every minute');
    expect(cronSummary('*/5 * * * *')).toBe('Every 5 minutes');
    expect(cronSummary('30 * * * *')).toBe('Every hour at :30');
  });

  it('treats day-of-week 7 as Sunday instead of "undefined"', () => {
    expect(cronSummary('0 8 * * 7')).toBe('Every Sunday at 08:00');
  });
});

describe('monthly + timezone fidelity', () => {
  it('builds a monthly cron on the chosen day', () => {
    const base = { ...emptyBotDraft(), name: 'b', objective: 'o', time: '09:30', dom: 15 };
    expect(buildTrigger({ ...base, schedule: 'monthly' })).toMatchObject({ type: 'cron', cron: '30 9 15 * *' });
  });

  it('round-trips a monthly cron back into a draft', () => {
    const b = bot({ trigger: { ...bot().trigger, type: 'cron', cron: '30 9 15 * *' } });
    const draft = draftFromBot(b);
    expect(draft.schedule).toBe('monthly');
    expect(draft.dom).toBe(15);
    expect(draft.time).toBe('09:30');
  });

  it('preserves the trigger timezone when editing', () => {
    const b = bot({ trigger: { ...bot().trigger, type: 'cron', cron: '0 8 * * *', timezone: 'Asia/Tokyo' } });
    const draft = draftFromBot(b);
    expect(draft.timezone).toBe('Asia/Tokyo');
    expect(buildTrigger(draft)).toMatchObject({ timezone: 'Asia/Tokyo' });
  });

  it('does not throw on an unparseable one-time date', () => {
    const draft = { ...emptyBotDraft(), schedule: 'once' as const, runAt: 'not-a-date' };
    expect(() => buildTrigger(draft)).not.toThrow();
  });
});

describe('interval clamp', () => {
  it('reports the true interval and clamps below the 30s floor', () => {
    const base = { ...emptyBotDraft(), schedule: 'interval' as const, intervalValue: 5, intervalUnit: 'seconds' as const };
    expect(intervalSecondsOf(base)).toBe(5);
    expect(buildTrigger(base)).toMatchObject({ intervalSeconds: 30 });
  });
});

describe('run behaviour policies', () => {
  it('maps a draft to execution/concurrency/retry objects', () => {
    const draft = {
      ...emptyBotDraft(),
      misfire: 'catch_up' as const,
      catchUpMax: 4,
      onConflict: 'queue_if_running' as const,
      maxRuns: 2,
      maxAttempts: 3,
      maxRuntimeS: 600,
    };
    expect(buildPolicies(draft)).toEqual({
      execution: { misfire: 'catch_up', catchUpMax: 4, maxRuntimeS: 600 },
      concurrency: { maxConcurrentRuns: 2, onConflict: 'queue_if_running' },
      retry: { maxAttempts: 3 },
    });
  });

  it('round-trips an existing bot\'s behaviour into a draft', () => {
    const b = bot({
      execution: { maxRuntimeS: 300, misfire: 'run_once', catchUpMax: 5, timeoutS: null },
      concurrency: { maxConcurrentRuns: 2, onConflict: 'cancel_previous' },
      retry: { maxAttempts: 3, initialBackoffS: 5, backoffMultiplier: 2, maxBackoffS: 300, jitter: true, retryableClasses: [], nonRetryableClasses: [] },
    });
    const draft = draftFromBot(b);
    expect(buildPolicies(draft)).toEqual({
      execution: { misfire: 'run_once', catchUpMax: 5, maxRuntimeS: 300 },
      concurrency: { maxConcurrentRuns: 2, onConflict: 'cancel_previous' },
      retry: { maxAttempts: 3 },
    });
  });
});

describe('per-bot model override', () => {
  it('builds a model override only when a model is pinned', () => {
    expect(buildModelConfig(emptyBotDraft())).toEqual({});
    const draft = { ...emptyBotDraft(), modelProvider: 'openai', model: 'gpt-4o' };
    expect(buildModelConfig(draft)).toEqual({ modelSettings: { model: 'gpt-4o', provider: 'openai' } });
  });

  it('round-trips a pinned model into a draft', () => {
    const b = bot({ action: { ...bot().action, config: { modelSettings: { provider: 'openai', model: 'gpt-4o' } } } });
    const draft = draftFromBot(b);
    expect(draft.model).toBe('gpt-4o');
    expect(draft.modelProvider).toBe('openai');
    expect(buildModelConfig(draft)).toEqual({ modelSettings: { model: 'gpt-4o', provider: 'openai' } });
  });

  it('exposes both halves of the pin so a chat turn can match a scheduled run', () => {
    const b = bot({ action: { ...bot().action, config: { modelSettings: { provider: 'openai', model: 'gpt-4o' } } } });
    expect(botModelPin(b)).toEqual({ provider: 'openai', model: 'gpt-4o' });
    expect(botModelPin(bot())).toEqual({});
  });
});

describe('event / condition trigger preservation', () => {
  const condition = { expression: 'drawdown > 0.1', edge: true, variables: ['drawdown'] };

  it('round-trips an event trigger instead of downgrading it to manual', () => {
    const b = bot({
      trigger: {
        ...bot().trigger,
        type: 'event',
        eventType: 'filing.created',
        eventFilter: { symbol: 'AAPL' },
      },
    });
    const draft = draftFromBot(b);
    expect(draft.schedule).toBe('event');
    expect(buildTrigger(draft)).toMatchObject({
      type: 'event',
      eventType: 'filing.created',
      eventFilter: { symbol: 'AAPL' },
    });
  });

  it('round-trips a condition trigger (e.g. a portfolio monitor)', () => {
    const b = bot({
      condition,
      trigger: { ...bot().trigger, type: 'condition', condition },
    });
    const draft = draftFromBot(b);
    expect(draft.schedule).toBe('condition');
    expect(buildTrigger(draft)).toMatchObject({ type: 'condition', condition });
  });
});

describe('isBotAutomation', () => {
  it('accepts tagged bots and monitors but rejects jobs / event rules', () => {
    expect(isBotAutomation({ id: 'a1', tags: ['bot'] })).toBe(true);
    expect(isBotAutomation({ id: 'mon_123', tags: [] })).toBe(true);
    expect(isBotAutomation({ id: 'job_1', tags: [] })).toBe(false);
    expect(isBotAutomation({ id: 'rule_1', tags: ['event-rule'] })).toBe(false);
  });
});

describe('time formatting', () => {
  it('formats durations', () => {
    expect(formatDuration('2026-01-01T00:00:00Z', '2026-01-01T00:00:45Z')).toBe('45s');
    expect(formatDuration('2026-01-01T00:00:00Z', '2026-01-01T00:02:05Z')).toBe('2m 5s');
    expect(formatDuration(null, null)).toBe('—');
  });

  it('formats relative time', () => {
    const now = Date.parse('2026-01-01T12:00:00Z');
    expect(formatRelative('2026-01-01T14:00:00Z', now)).toBe('in 2 hours');
    expect(formatRelative('2026-01-01T11:55:00Z', now)).toBe('5 minutes ago');
  });
});

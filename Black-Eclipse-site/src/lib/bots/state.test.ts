import { describe, expect, it } from 'vitest';
import type { AutomationView } from '@/lib/harness/automation-client';
import {
  BOT_FILTERS,
  botMatchesFilter,
  botMatchesSearch,
  buildTrigger,
  cronSummary,
  detectSchedule,
  draftFromBot,
  emptyBotDraft,
  executionLabel,
  executionTone,
  formatDuration,
  formatRelative,
  isLiveExecution,
  isTerminalExecution,
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

  it('stays manual when there is no schedule phrase', () => {
    expect(detectSchedule('answer questions about my holdings')).toBeNull();
    expect(detectSchedule('')).toBeNull();
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

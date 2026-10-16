// ── Bot workspace logic (pure) ───────────────────────────────────────────────
// Everything the Bots workspace derives from server data that is NOT rendering:
// the backend→UI state vocabulary, real filters, search, human schedule
// summaries, and the draft→trigger translation used by the creation flow.
// Kept pure and dependency-free so it is unit-testable without a DOM.

import type {
  AutomationState,
  AutomationView,
  BreakerState,
  CreateAutomationInput,
  ExecutionState,
  TriggerKind,
  TriggerView,
} from '@/lib/harness/automation-client';

// ── Execution state vocabulary ───────────────────────────────────────────────

/** A run is finished once it reaches one of these; polling must stop. */
export const TERMINAL_EXECUTION_STATES: ReadonlySet<ExecutionState> = new Set([
  'completed', 'failed', 'cancelled', 'timed_out', 'skipped', 'blocked',
]);

/** A run is "in flight" — queued, starting, running, waiting or retrying. */
const LIVE_EXECUTION_STATES: ReadonlySet<ExecutionState> = new Set([
  'triggered', 'queued', 'running', 'waiting', 'retrying',
]);

export function isTerminalExecution(state: ExecutionState): boolean {
  return TERMINAL_EXECUTION_STATES.has(state);
}

export function isLiveExecution(state: ExecutionState): boolean {
  return LIVE_EXECUTION_STATES.has(state);
}

/** Restrained status colors — green/amber/rose/sky/muted only. */
export type Tone = 'positive' | 'warning' | 'danger' | 'info' | 'muted';

export function executionTone(state: ExecutionState): Tone {
  switch (state) {
    case 'completed':
      return 'positive';
    case 'failed':
    case 'timed_out':
      return 'danger';
    case 'blocked':
      return 'warning';
    case 'running':
    case 'retrying':
      return 'info';
    case 'waiting':
      return 'warning';
    case 'queued':
    case 'triggered':
      return 'info';
    default:
      return 'muted';
  }
}

/** A short, human label for a backend execution state. */
export function executionLabel(state: ExecutionState): string {
  const map: Record<ExecutionState, string> = {
    triggered: 'Starting',
    queued: 'Queued',
    running: 'Running',
    waiting: 'Waiting for approval',
    retrying: 'Retrying',
    completed: 'Completed',
    failed: 'Failed',
    cancelled: 'Cancelled',
    timed_out: 'Timed out',
    blocked: 'Blocked',
    skipped: 'Skipped',
  };
  return map[state] ?? state;
}

export function lifecycleLabel(state: AutomationState): string {
  const map: Record<AutomationState, string> = {
    draft: 'Draft',
    validating: 'Validating',
    active: 'Active',
    paused: 'Paused',
    disabled: 'Disabled',
    archived: 'Archived',
  };
  return map[state] ?? state;
}

export function breakerLabel(state: BreakerState): string {
  const map: Record<BreakerState, string> = {
    closed: 'Healthy',
    half_open: 'Recovering',
    open: 'Paused after repeated failures',
  };
  return map[state] ?? state;
}

// ── Attention ────────────────────────────────────────────────────────────────

/** A bot needs attention when its breaker tripped or it has consecutive
 *  failures. Both are real fields on the list payload, so the filter is exact. */
export function needsAttention(bot: AutomationView): boolean {
  return bot.breaker === 'open' || bot.consecutiveFailures > 0;
}

// ── Filters ──────────────────────────────────────────────────────────────────

export type BotFilter = 'all' | 'active' | 'paused' | 'running' | 'attention';

export interface FilterDef {
  id: BotFilter;
  /** i18n key for the filter chip label. */
  labelKey: string;
}

export const BOT_FILTERS: readonly FilterDef[] = [
  { id: 'all', labelKey: 'bots.filter.all' },
  { id: 'active', labelKey: 'bots.filter.active' },
  { id: 'paused', labelKey: 'bots.filter.paused' },
  { id: 'running', labelKey: 'bots.filter.running' },
  { id: 'attention', labelKey: 'bots.filter.attention' },
];

/**
 * Whether a bot belongs to a filter. `running` is data-driven: the caller passes
 * the ids with a live execution (from real run records), never a guess.
 */
export function botMatchesFilter(bot: AutomationView, filter: BotFilter, runningIds: ReadonlySet<string>): boolean {
  switch (filter) {
    case 'active':
      return bot.state === 'active';
    case 'paused':
      return bot.state === 'paused';
    case 'running':
      return runningIds.has(bot.id);
    case 'attention':
      return needsAttention(bot);
    default:
      return true;
  }
}

/** Case-insensitive search over the fields a user would recognize. */
export function botMatchesSearch(bot: AutomationView, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return (
    bot.name.toLowerCase().includes(q) ||
    (bot.description ?? '').toLowerCase().includes(q) ||
    bot.action.objective?.toLowerCase().includes(q) === true ||
    bot.tags.some((t) => t.toLowerCase().includes(q))
  );
}

// ── Triggers / schedules ─────────────────────────────────────────────────────

export function triggerKindLabel(kind: TriggerKind): string {
  const map: Record<TriggerKind, string> = {
    manual: 'On demand',
    one_time: 'One-time',
    interval: 'Repeats on an interval',
    cron: 'Recurring',
    event: 'On an event',
    condition: 'When a condition is met',
  };
  return map[kind] ?? kind;
}

/** Group a trigger into the coarse "manual / one-time / recurring / event"
 *  vocabulary the UI shows. */
export function triggerClass(kind: TriggerKind): 'manual' | 'once' | 'recurring' | 'event' {
  switch (kind) {
    case 'manual':
      return 'manual';
    case 'one_time':
      return 'once';
    case 'event':
    case 'condition':
      return 'event';
    default:
      return 'recurring';
  }
}

const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

function pad2(n: number): string {
  return String(n).padStart(2, '0');
}

/** A best-effort human summary of a cron expression; falls back honestly. */
export function cronSummary(expr: string): string {
  const parts = expr.trim().split(/\s+/);
  if (parts.length !== 5) return `Custom schedule (${expr})`;
  const [min, hour, dom, mon, dow] = parts;
  const time = /^\d+$/.test(min) && /^\d+$/.test(hour) ? `${pad2(Number(hour))}:${pad2(Number(min))}` : null;
  const at = time ? ` at ${time}` : '';
  if (dom === '*' && mon === '*' && dow === '*') return `Every day${at}`;
  if (dom === '*' && mon === '*' && dow === '1-5') return `Every weekday${at}`;
  if (dom === '*' && mon === '*' && /^\d$/.test(dow)) return `Every ${WEEKDAYS[Number(dow)]}${at}`;
  if (dom === '*' && mon === '*' && /^[0-6](,[0-6])+$/.test(dow)) {
    const names = dow.split(',').map((d) => WEEKDAYS[Number(d)]).join(', ');
    return `${names}${at}`;
  }
  if (/^\d+$/.test(dom) && mon === '*' && dow === '*') return `Monthly on day ${dom}${at}`;
  return `Custom schedule (${expr})`;
}

function intervalSummary(seconds: number): string {
  if (seconds % 86400 === 0) return `Every ${seconds / 86400} day${seconds / 86400 === 1 ? '' : 's'}`;
  if (seconds % 3600 === 0) return `Every ${seconds / 3600} hour${seconds / 3600 === 1 ? '' : 's'}`;
  if (seconds % 60 === 0) {
    const mins = Math.round(seconds / 60);
    return `Every ${mins} minute${mins === 1 ? '' : 's'}`;
  }
  return `Every ${seconds} second${seconds === 1 ? '' : 's'}`;
}

/** A single-line, plain-language schedule summary for a trigger. */
export function scheduleSummary(trigger: TriggerView): string {
  switch (trigger.type) {
    case 'interval':
      return trigger.intervalSeconds ? intervalSummary(trigger.intervalSeconds) : 'Repeats on an interval';
    case 'cron':
      return trigger.cron ? cronSummary(trigger.cron) : 'Recurring';
    case 'one_time':
      return trigger.runAt ? `Once on ${formatDateTime(trigger.runAt)}` : 'Runs once';
    case 'event':
      return `When ${trigger.eventType ?? 'an event'} occurs`;
    case 'condition':
      return 'When a condition is met';
    default:
      return 'On demand — runs only when you start it';
  }
}

// ── Time formatting ──────────────────────────────────────────────────────────

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

/** Human relative time ("in 2 hours", "5 minutes ago"). */
export function formatRelative(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return '—';
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return iso;
  const delta = t - now;
  const abs = Math.abs(delta);
  const future = delta > 0;
  const units: Array<[number, string]> = [
    [86_400_000, 'day'],
    [3_600_000, 'hour'],
    [60_000, 'minute'],
  ];
  for (const [ms, unit] of units) {
    if (abs >= ms) {
      const n = Math.round(abs / ms);
      return future ? `in ${n} ${unit}${n === 1 ? '' : 's'}` : `${n} ${unit}${n === 1 ? '' : 's'} ago`;
    }
  }
  return future ? 'in a moment' : 'just now';
}

export function formatDuration(startIso: string | null | undefined, endIso: string | null | undefined): string {
  if (!startIso || !endIso) return '—';
  const start = new Date(startIso).getTime();
  const end = new Date(endIso).getTime();
  if (Number.isNaN(start) || Number.isNaN(end) || end < start) return '—';
  const s = Math.round((end - start) / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return rem ? `${m}m ${rem}s` : `${m}m`;
}

export function localTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
}

// ── Creation draft ───────────────────────────────────────────────────────────

/** The agent presets a bot can run as (the backend's closed set). */
export const BOT_AGENTS: ReadonlyArray<{ id: string; label: string }> = [
  { id: 'eclipse-agent', label: 'Eclipse' },
  { id: 'code-navigator', label: 'Code Navigator' },
  { id: 'code-agent', label: 'Code Agent' },
];

export type ScheduleChoice = 'manual' | 'once' | 'daily' | 'weekdays' | 'weekly' | 'interval' | 'cron';

export interface BotDraft {
  name: string;
  objective: string;
  agentId: string;
  schedule: ScheduleChoice;
  /** "HH:MM" for daily/weekdays/weekly. */
  time: string;
  /** 0=Sunday..6=Saturday for weekly. */
  weekday: number;
  intervalValue: number;
  intervalUnit: 'seconds' | 'minutes' | 'hours' | 'days';
  cron: string;
  runAt: string;
}

export function emptyBotDraft(): BotDraft {
  return {
    name: '',
    objective: '',
    agentId: 'eclipse-agent',
    schedule: 'manual',
    time: '08:00',
    weekday: 1,
    intervalValue: 1,
    intervalUnit: 'days',
    cron: '0 8 * * *',
    runAt: '',
  };
}

function timeParts(time: string): { hour: number; minute: number } {
  const [h, m] = time.split(':').map((n) => Number(n));
  return {
    hour: Number.isFinite(h) ? h : 8,
    minute: Number.isFinite(m) ? m : 0,
  };
}

/** Turn a draft into the trigger object the API expects. */
export function buildTrigger(draft: BotDraft): CreateAutomationInput['trigger'] {
  const timezone = localTimezone();
  const { hour, minute } = timeParts(draft.time);
  switch (draft.schedule) {
    case 'once':
      return { type: 'one_time', runAt: new Date(draft.runAt).toISOString(), timezone };
    case 'daily':
      return { type: 'cron', cron: `${minute} ${hour} * * *`, timezone };
    case 'weekdays':
      return { type: 'cron', cron: `${minute} ${hour} * * 1-5`, timezone };
    case 'weekly':
      return { type: 'cron', cron: `${minute} ${hour} * * ${draft.weekday}`, timezone };
    case 'interval': {
      const mult = draft.intervalUnit === 'days' ? 86400
        : draft.intervalUnit === 'hours' ? 3600
        : draft.intervalUnit === 'minutes' ? 60
        : 1;
      return { type: 'interval', intervalSeconds: Math.max(30, draft.intervalValue * mult), timezone };
    }
    case 'cron':
      return { type: 'cron', cron: draft.cron.trim(), timezone };
    default:
      return { type: 'manual', timezone };
  }
}

export interface DraftIssue {
  field: keyof BotDraft | 'schedule';
  message: string;
}

/** Validate a draft before saving. Mirrors the backend's hard rules so the user
 *  sees the error beside the field, not as a raw API failure. */
export function validateDraft(draft: BotDraft): DraftIssue[] {
  const issues: DraftIssue[] = [];
  if (!draft.name.trim()) issues.push({ field: 'name', message: 'Give the bot a name.' });
  if (!draft.objective.trim()) issues.push({ field: 'objective', message: 'Describe what the bot should do.' });
  if (draft.schedule === 'once') {
    if (!draft.runAt) issues.push({ field: 'runAt', message: 'Pick a date and time to run.' });
    else if (new Date(draft.runAt).getTime() <= Date.now()) {
      issues.push({ field: 'runAt', message: 'Choose a time in the future.' });
    }
  }
  if (draft.schedule === 'interval' && draft.intervalValue < 1) {
    issues.push({ field: 'intervalValue', message: 'The interval must be at least 1.' });
  }
  if (draft.schedule === 'cron') {
    const parts = draft.cron.trim().split(/\s+/);
    if (parts.length !== 5) issues.push({ field: 'cron', message: 'A cron schedule has five fields.' });
  }
  return issues;
}

/** The human-readable schedule line shown in the review summary. */
export function summarizeDraft(draft: BotDraft): string {
  return scheduleSummary(buildTrigger(draft) as TriggerView);
}

/** Propose a short, human name from an objective. Deterministic, no model call:
 *  strips leading verbs/filler and title-cases the first few meaningful words. */
export function suggestName(objective: string): string {
  const cleaned = objective
    .replace(/[.\n]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  if (!cleaned) return '';
  const stop = new Set([
    'a', 'an', 'the', 'my', 'our', 'me', 'every', 'each', 'that', 'which', 'and',
    'to', 'of', 'for', 'on', 'in', 'at', 'with', 'from', 'it', 'this', 'create',
    'make', 'build', 'run', 'please', 'summarize', 'review', 'check', 'monitor',
  ]);
  const words = cleaned.split(' ').filter((w) => !stop.has(w.toLowerCase()));
  const picked = words.slice(0, 4).map((w) => w.charAt(0).toUpperCase() + w.slice(1));
  return picked.join(' ').slice(0, 60).trim();
}

/** Seed a draft from an existing bot (for editing). */
export function draftFromBot(bot: AutomationView): BotDraft {
  const base = emptyBotDraft();
  const draft: BotDraft = {
    ...base,
    name: bot.name,
    objective: bot.action.objective ?? bot.description ?? '',
    agentId: bot.action.agentId ?? 'eclipse-agent',
  };
  const trig = bot.trigger;
  if (trig.type === 'interval') {
    const s = trig.intervalSeconds ?? 3600;
    if (s % 86400 === 0) { draft.schedule = 'interval'; draft.intervalValue = s / 86400; draft.intervalUnit = 'days'; }
    else if (s % 3600 === 0) { draft.schedule = 'interval'; draft.intervalValue = s / 3600; draft.intervalUnit = 'hours'; }
    else if (s % 60 === 0) { draft.schedule = 'interval'; draft.intervalValue = Math.round(s / 60); draft.intervalUnit = 'minutes'; }
    else { draft.schedule = 'interval'; draft.intervalValue = s; draft.intervalUnit = 'seconds'; }
  } else if (trig.type === 'cron' && trig.cron) {
    const parts = trig.cron.trim().split(/\s+/);
    if (parts.length === 5) {
      const [min, hour, dom, mon, dow] = parts;
      if (/^\d+$/.test(min) && /^\d+$/.test(hour)) draft.time = `${pad2(Number(hour))}:${pad2(Number(min))}`;
      if (dom === '*' && mon === '*' && dow === '*') draft.schedule = 'daily';
      else if (dom === '*' && mon === '*' && dow === '1-5') draft.schedule = 'weekdays';
      else if (dom === '*' && mon === '*' && /^\d$/.test(dow)) { draft.schedule = 'weekly'; draft.weekday = Number(dow); }
      else { draft.schedule = 'cron'; draft.cron = trig.cron; }
    } else {
      draft.schedule = 'cron';
      draft.cron = trig.cron;
    }
  } else if (trig.type === 'one_time') {
    draft.schedule = 'once';
    if (trig.runAt) {
      const d = new Date(trig.runAt);
      if (!Number.isNaN(d.getTime())) {
        const local = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
        draft.runAt = local.toISOString().slice(0, 16);
      }
    }
  } else {
    draft.schedule = 'manual';
  }
  return draft;
}

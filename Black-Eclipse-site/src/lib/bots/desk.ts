// ── Desks: a saved, user-authored team run ────────────────────────────────────
// A desk is an automation whose action is `run_team` and whose `config.team` is a
// TeamDefinition (docs/harness/desks-plan.md). This module is the ONE mapping
// between the builder's draft and that definition, so the builder, the runner and
// an edited desk all agree. Nothing here runs anything.

'use client';

import type {
  ActionKind,
  AutomationView,
  CreateAutomationInput,
} from '@/lib/harness/clients/automation-client';
import type { TeamDefinitionView, TeamMemberView, TeamSubtaskView } from '@/lib/harness/clients/team-client';

export const DESK_TAG = 'desk';

/** Tools a stage may use. `order_submit` is deliberately absent everywhere: a
 *  desk proposes (`order_preview`), a trading bot executes. */
export const ROLE_TEMPLATES = {
  research: {
    label: 'Research',
    objective: 'Build the evidence base for: {{objective}}',
    instructions:
      'Build the evidence base every later stage will rely on. Use retrieved data only, ' +
      'cite the source and as-of date for every material figure, and write UNAVAILABLE ' +
      'instead of estimating. Name the strongest fact on each side and what is still unknown.',
    tools: [
      'research_search', 'research_search_news', 'research_retrieve_source',
      'market_get_quote', 'market_get_ohlcv', 'macro_get_series',
      'portfolio_list', 'portfolio_get', 'read_run_output',
    ],
    expectedKeys: 'brief,evidence_refs',
  },
  challenge: {
    label: 'Challenge',
    objective: 'Argue the strongest honest case against the brief: {{objective}}',
    instructions:
      'Read the completed brief with read_run_output and argue the strongest honest ' +
      'counter-case. Concede the point you cannot rebut. Never average a disagreement ' +
      'away and never present an unsupported claim as fact.',
    tools: [
      'research_search', 'research_search_news', 'market_get_quote',
      'read_run_output',
    ],
    expectedKeys: 'case,conceded_point',
  },
  proposal: {
    label: 'Proposal',
    objective: 'Turn the record into a fully specified proposal: {{objective}}',
    instructions:
      'Read the prerequisite memos and produce a fully specified proposal (instrument, ' +
      'direction, size, entry, stop, horizon). Call order_preview for the operator to ' +
      'confirm. Never claim an order was sent and never state a fill you did not observe.',
    tools: [
      'get_quote', 'get_historical_prices', 'get_orderbook', 'portfolio_get',
      'portfolio_calculate_exposure', 'order_preview', 'read_run_output',
    ],
    expectedKeys: 'instrument,direction,size,entry,stop',
  },
  risk: {
    label: 'Risk',
    objective: 'Independently review the proposal against the real portfolio: {{objective}}',
    instructions:
      'Review the proposal against the actual portfolio and the evidence. Return a verdict ' +
      '(APPROVE / APPROVE WITH LIMITS / VETO), the limits, and every limit that is breached. ' +
      'Do not defer to the proposer.',
    tools: [
      'portfolio_get', 'portfolio_calculate_risk', 'portfolio_calculate_exposure',
      'portfolio_stress_test', 'market_get_quote', 'read_run_output',
    ],
    expectedKeys: 'verdict,limits,breaches',
  },
  decision: {
    label: 'Decision',
    objective: 'Make the final decision from the record: {{objective}}',
    instructions:
      'Read the brief, the challenge, the proposal and the risk verdict. Return a DECISION ' +
      '(APPROVE / APPROVE WITH CONDITIONS / RESIZE / HOLD / REJECT) with the conditions and ' +
      'invalidation triggers, and say how each unresolved disagreement was treated. Never ' +
      'place an order.',
    tools: ['read_run_output'],
    expectedKeys: 'decision,conditions',
  },
} as const;

export type DeskRoleTemplate = keyof typeof ROLE_TEMPLATES;

export interface DeskStage {
  /** Stable subtask id; also the suffix of the stage's runtime agent id. */
  key: string;
  label: string;
  role: DeskRoleTemplate;
  objective: string;
  instructions: string;
  tools: string[];
  /** Earlier stage keys this stage reads. */
  dependsOn: string[];
  expectedKeys: string;
  review: boolean;
}

export interface DeskTrigger {
  kind: 'manual' | 'interval' | 'event';
  /** Interval in minutes (the engine's floor is 30 s; the UI offers minutes). */
  intervalMinutes: number;
  /** The monitor bot whose completion wakes this desk. */
  sourceBotId: string;
}

export interface DeskDraft {
  /** Stable team id. It prefixes every member agent id, so two desks that both
   *  have a "research" stage never share an A2A agent. */
  id: string;
  name: string;
  description: string;
  objective: string;
  trigger: DeskTrigger;
  stages: DeskStage[];
}

function randomId(): string {
  return `desk_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
}

/** A fresh, stable id for a new desk (also used when duplicating one). */
export function newDeskId(): string {
  return randomId();
}

function slug(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 32) || 'stage';
}

export function newDeskStage(role: DeskRoleTemplate, key: string, dependsOn: string[] = []): DeskStage {
  const template = ROLE_TEMPLATES[role];
  return {
    key,
    label: template.label,
    role,
    objective: template.objective,
    instructions: template.instructions,
    tools: [...template.tools],
    dependsOn,
    expectedKeys: template.expectedKeys,
    review: role === 'risk' || role === 'decision',
  };
}

/** A 3-stage starter that is valid as-is: research → challenge → decision. */
export function emptyDeskDraft(): DeskDraft {
  return {
    id: newDeskId(),
    name: '',
    description: '',
    objective: '',
    trigger: { kind: 'manual', intervalMinutes: 15, sourceBotId: '' },
    stages: [
      newDeskStage('research', 'research'),
      newDeskStage('challenge', 'challenge', ['research']),
      newDeskStage('decision', 'decision', ['research', 'challenge']),
    ],
  };
}

export function isDesk(bot: Pick<AutomationView, 'action'>): boolean {
  return bot.action?.type === 'run_team';
}

export function deskTeamOf(bot: Pick<AutomationView, 'action'>): TeamDefinitionView | null {
  const team = (bot.action?.config ?? {})['team'];
  if (!team || typeof team !== 'object') return null;
  const candidate = team as TeamDefinitionView;
  return Array.isArray(candidate.members) && Array.isArray(candidate.subtasks) ? candidate : null;
}

/** Replace the {{objective}} token with the desk's question. */
export function resolveObjective(text: string, objective: string): string {
  return text.replace(/\{\{\s*objective\s*\}\}/gi, objective.trim() || 'this question');
}

function memberAgentId(draftId: string, key: string): string {
  return `${draftId}-${key}`.replace(/[^A-Za-z0-9._-]/g, '-').slice(0, 80);
}

function stageOutput(keys: string): Record<string, string> {
  const parsed = keys.split(',').map((k) => k.trim()).filter(Boolean);
  return Object.fromEntries(parsed.map((key) => [key, 'string']));
}

export function deskToTeam(draft: DeskDraft): TeamDefinitionView {
  const objective = draft.objective.trim();
  const members: TeamMemberView[] = draft.stages.map((stage) => ({
    agentId: memberAgentId(draft.id, stage.key),
    label: stage.label.trim() || stage.key,
    role: stage.role,
    capabilities: [stage.key],
    tools: stage.tools,
    instructions: `${stage.instructions}\n\nDesk question for this run: ${objective || '(not set)'}`,
  }));
  const subtasks: TeamSubtaskView[] = draft.stages.map((stage) => ({
    id: stage.key,
    objective: resolveObjective(stage.objective, objective),
    assignedAgentId: memberAgentId(draft.id, stage.key),
    dependsOn: stage.dependsOn.filter((dep) => dep !== stage.key),
    expectedOutput: stageOutput(stage.expectedKeys),
    review: stage.review,
  }));
  return {
    id: draft.id,
    name: draft.name.trim() || 'Desk',
    objective,
    agentId: 'eclipse-orchestrator',
    members,
    subtasks,
    policy: {
      delegationEnabled: true,
      maxDepth: 8,
      maxChildren: Math.max(draft.stages.length, 1),
      maxConcurrency: Math.max(1, Math.min(3, draft.stages.length)),
      perAgentConcurrency: 1,
      maxTasks: draft.stages.length + 3,
      maxCost: 25,
      maxRuntimeMs: 900_000,
      requireReview: true,
      reviewStrictness: 'STRICT',
      optionalFailurePolicy: 'REQUIRE_ALL',
      requireApproval: false,
    },
    metadata: { desk: true },
  };
}

/** The one create payload the builder uses (tags make it a Bots-mode bot). */
export function deskCreateInput(draft: DeskDraft): CreateAutomationInput {
  const team = deskToTeam(draft);
  const trigger =
    draft.trigger.kind === 'event'
      ? {
          type: 'event' as const,
          eventType: 'automation.completed' as string | null,
          eventFilter: draft.trigger.sourceBotId
            ? { automationId: draft.trigger.sourceBotId }
            : {},
        }
      : draft.trigger.kind === 'interval'
        ? {
            type: 'interval' as const,
            intervalSeconds: Math.max(60, Math.round(draft.trigger.intervalMinutes * 60)),
          }
        : { type: 'manual' as const };
  return {
    name: draft.name.trim() || 'Desk',
    description: draft.description.trim() || 'A team of bots working one question.',
    state: 'active',
    trigger,
    action: {
      type: 'run_team' as ActionKind,
      objective: draft.objective.trim() || team.name,
      config: {
        teamId: team.id,
        team,
        ...(draft.trigger.kind === 'event' && draft.trigger.sourceBotId
          ? { contextAutomationId: draft.trigger.sourceBotId }
          : {}),
      },
    },
    tags: ['bot', DESK_TAG],
  };
}

/** Hydrate the builder from a saved desk. Empty when the definition is unusable. */
export function deskDraftFromAutomation(
  bot: Pick<AutomationView, 'action' | 'trigger'>,
): DeskDraft {
  const team = deskTeamOf(bot);
  if (!team) return emptyDeskDraft();
  const stages: DeskStage[] = team.subtasks.map((subtask) => {
    const member = team.members.find((m) => m.agentId === subtask.assignedAgentId);
    const key = subtask.id;
    return {
      key,
      label: member?.label?.trim() || key,
      role: (member?.role && member.role in ROLE_TEMPLATES
        ? member.role
        : 'research') as DeskRoleTemplate,
      objective: subtask.objective,
      instructions: member?.instructions ?? '',
      tools: member?.tools ?? [],
      dependsOn: subtask.dependsOn ?? [],
      expectedKeys: Object.keys(subtask.expectedOutput ?? {}).join(','),
      review: subtask.review ?? false,
    };
  });
  return {
    id: team.id,
    name: team.name,
    description: '',
    objective: team.objective ?? '',
    trigger: triggerFromAutomation(bot),
    stages: stages.length ? stages : emptyDeskDraft().stages,
  };
}

function triggerFromAutomation(bot: Pick<AutomationView, 'action' | 'trigger'>): DeskTrigger {
  const source = String(
    (bot.action?.config ?? {})['contextAutomationId']
      ?? (bot.trigger?.eventFilter ?? {})['automationId']
      ?? '',
  );
  if (bot.trigger?.type === 'event') {
    return { kind: 'event', intervalMinutes: 15, sourceBotId: source };
  }
  if (bot.trigger?.type === 'interval') {
    return {
      kind: 'interval',
      intervalMinutes: Math.max(1, Math.round((bot.trigger.intervalSeconds ?? 900) / 60)),
      sourceBotId: source,
    };
  }
  return { kind: 'manual', intervalMinutes: 15, sourceBotId: source };
}

/**
 * Client-side reasons a draft cannot be saved. The server (`POST /team/validate`)
 * is the real gate; these exist so the common mistake is explained in place and
 * a cycle never reaches the API.
 */
export function deskIssues(draft: DeskDraft): string[] {
  const issues: string[] = [];
  if (!draft.name.trim()) issues.push('Give the desk a name.');
  if (!draft.objective.trim()) issues.push('Write the question every stage works on.');
  if (draft.stages.length < 2) issues.push('A desk needs at least two stages — use a bot for one agent.');
  if (draft.trigger.kind === 'interval' && draft.trigger.intervalMinutes < 1) {
    issues.push('An interval desk needs at least one minute between runs.');
  }
  if (draft.trigger.kind === 'event' && !draft.trigger.sourceBotId) {
    issues.push('Choose the bot whose finished run wakes this desk.');
  }
  const seen = new Set<string>();
  const keys = new Set(draft.stages.map((s) => s.key));
  for (const stage of draft.stages) {
    if (!stage.key.trim()) issues.push('Every stage needs an id.');
    if (seen.has(stage.key)) issues.push(`Stage id "${stage.key}" is used twice.`);
    seen.add(stage.key);
    if (!stage.label.trim()) issues.push(`Stage "${stage.key}" needs a name.`);
    if (!stage.instructions.trim()) issues.push(`Stage "${stage.key}" needs instructions.`);
    for (const dep of stage.dependsOn) {
      if (dep === stage.key) issues.push(`Stage "${stage.key}" cannot depend on itself.`);
      else if (!keys.has(dep)) issues.push(`Stage "${stage.key}" depends on unknown stage "${dep}".`);
    }
    if (stage.tools.some((tool) => tool === 'order_submit' || tool === 'place_order')) {
      issues.push(`Stage "${stage.key}" may propose (order_preview) but not submit an order.`);
    }
  }
  return issues;
}

/** A short, stable id for a new stage, unique within the draft. */
export function nextStageKey(draft: DeskDraft, role: DeskRoleTemplate): string {
  const base = slug(role);
  const taken = new Set(draft.stages.map((s) => s.key));
  if (!taken.has(base)) return base;
  let index = 2;
  while (taken.has(`${base}-${index}`)) index += 1;
  return `${base}-${index}`;
}

export function roleLabel(role: DeskRoleTemplate): string {
  return ROLE_TEMPLATES[role].label;
}

export function stageAgentId(team: TeamDefinitionView | null, key: string): string | null {
  const subtask = team?.subtasks.find((s) => s.id === key);
  return subtask?.assignedAgentId ?? null;
}

/**
 * The `config` a duplicated desk should carry. A copy gets a NEW team id and new
 * member agent ids: the A2A registry keeps the first registration for an id, so a
 * verbatim copy would silently run the original stage's instructions.
 */
export function duplicateDeskConfig(bot: AutomationView): Record<string, unknown> | null {
  const team = deskTeamOf(bot);
  if (!team) return null;
  const draft = deskDraftFromAutomation(bot);
  draft.id = newDeskId();
  const copy = deskToTeam(draft);
  return { ...(bot.action.config ?? {}), teamId: copy.id, team: copy };
}

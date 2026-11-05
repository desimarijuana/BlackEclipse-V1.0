// ── Agent choices (pure) ─────────────────────────────────────────────────────
// Extracted from the hook so the ordering and the "saved value is unknown"
// fallback can be unit-tested without React. No fetch, no state.

import type { AgentPresetSummary } from './client';

export interface AgentChoiceBuiltin {
  id: string;
  name: string;
  description?: string;
}

export type AgentChoiceSource = 'builtin' | 'preset' | 'unknown';

export interface AgentChoice {
  id: string;
  label: string;
  description?: string;
  source: AgentChoiceSource;
  /** True for an archived preset — still selectable so an edit cannot retarget. */
  archived?: boolean;
  version?: number;
}

export interface MergeAgentChoicesInput {
  builtins: ReadonlyArray<AgentChoiceBuiltin>;
  presets: ReadonlyArray<AgentPresetSummary>;
  /** The value already saved on the draft/bot. Never dropped, even if unknown. */
  currentId?: string;
}

/**
 * Built-ins first, then user presets by name, then — if the saved value matches
 * nothing the runtime reported — that value itself, labelled honestly. Dropping
 * an unknown id would silently rewrite a bot's brain on the next save.
 */
export function mergeAgentChoices(input: MergeAgentChoicesInput): AgentChoice[] {
  const out: AgentChoice[] = [];
  const seen = new Set<string>();

  for (const builtin of input.builtins) {
    const id = builtin.id.trim();
    if (!id || seen.has(id)) continue;
    seen.add(id);
    out.push({
      id,
      label: builtin.name,
      ...(builtin.description ? { description: builtin.description } : {}),
      source: 'builtin',
    });
  }

  const presets = [...input.presets].sort((a, b) => a.name.localeCompare(b.name));
  for (const preset of presets) {
    const id = preset.id.trim();
    if (!id || seen.has(id)) continue;
    seen.add(id);
    out.push({
      id,
      label: preset.name,
      ...(preset.description ? { description: preset.description } : {}),
      source: 'preset',
      ...(preset.archived ? { archived: true } : {}),
      ...(typeof preset.version === 'number' ? { version: preset.version } : {}),
    });
  }

  const current = input.currentId?.trim();
  if (current && !seen.has(current)) {
    out.push({
      id: current,
      label: `${current} (not found)`,
      description: 'This agent no longer exists. Pick another one before saving.',
      source: 'unknown',
    });
  }

  return out;
}

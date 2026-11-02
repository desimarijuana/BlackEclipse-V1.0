'use client';

// ── Agent choices — live loader ──────────────────────────────────────────────
// The ONE list a surface should offer when it asks "which agent runs this?".
// It is built from the live runtime (built-ins + the operator's own presets),
// never from a hardcoded array, so a preset created in Settings › Agents shows
// up everywhere. The merge/order/fallback rules live in `./choices`.

import { useEffect, useMemo, useState } from 'react';
import {
  BUILT_IN_AGENTS, listAgentPresets, listBuiltInAgents, type AgentPresetSummary,
} from './client';
import { mergeAgentChoices, type AgentChoice, type AgentChoiceBuiltin } from './choices';

export interface AgentChoicesState {
  choices: AgentChoice[];
  loading: boolean;
  error: string | null;
}

/**
 * Load the live agent list. Missing endpoints degrade to the built-in three
 * rather than an empty picker, and an archived preset is included so an existing
 * bot that points at one can still be edited.
 *
 * `currentId` is appended when the runtime does not know it (deleted preset), so
 * the picker can show the saved value instead of an empty trigger.
 */
export function useAgentChoices(enabled = true, currentId?: string): AgentChoicesState {
  const [builtins, setBuiltins] = useState<AgentChoiceBuiltin[]>(
    () => BUILT_IN_AGENTS.map(({ id, name, description }) => ({ id, name, description })),
  );
  const [presets, setPresets] = useState<AgentPresetSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled) return;
    let live = true;
    setLoading(true);
    void Promise.allSettled([listBuiltInAgents(), listAgentPresets(true)]).then(([builtinsResult, presetsResult]) => {
      if (!live) return;
      if (builtinsResult.status === 'fulfilled' && builtinsResult.value.length > 0) {
        setBuiltins(builtinsResult.value.map(({ id, name }) => ({ id, name })));
      }
      if (presetsResult.status === 'fulfilled') setPresets(presetsResult.value);
      const bothFailed = builtinsResult.status === 'rejected' && presetsResult.status === 'rejected';
      setError(bothFailed ? 'The agent list is unavailable right now.' : null);
      setLoading(false);
    });
    return () => { live = false; };
  }, [enabled]);

  const choices = useMemo(
    () => mergeAgentChoices({ builtins, presets, currentId }),
    [builtins, presets, currentId],
  );

  return { choices, loading, error };
}

"use client";

// ── useReasoningEffort — the composer's per-question effort override ─────────
// The Settings › AI control pins the GLOBAL default (`LLMConfig.reasoningEffort`,
// persisted server-side). This is the composer control: a per-question override
// that applies to the next run only and never touches the saved default. It is
// persisted locally (like the composer's model choice) so it survives a reload,
// and it sends NO requirement on Auto — the run falls back to the operator's
// saved default and, failing that, the runtime's task profile.

import { useCallback, useEffect, useState } from "react";
import {
  effortAt,
  effortIndex,
  isReasoningLevel,
  type ReasoningLevel,
} from "./reasoning";

const STORAGE_KEY = "be_reasoning_effort_v1";

function readStored(): ReasoningLevel | undefined {
  if (typeof window === "undefined") return undefined;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return isReasoningLevel(raw) ? raw : undefined;
  } catch {
    return undefined;
  }
}

function writeStored(effort: ReasoningLevel | undefined): void {
  if (typeof window === "undefined") return;
  try {
    if (effort) window.localStorage.setItem(STORAGE_KEY, effort);
    else window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Storage unavailable — the choice still applies for this session.
  }
}

export interface ReasoningEffortState {
  /** The per-question override, or `undefined` for Auto (no override). */
  effort: ReasoningLevel | undefined;
  /** Index into `EFFORT_STOPS` for a slider (Auto = 0). */
  index: number;
  /** Set by slider index (clamped; Auto = the first stop). */
  setIndex: (index: number) => void;
  /** Set by value (`undefined` clears back to Auto). */
  setEffort: (effort: ReasoningLevel | undefined) => void;
}

export function useReasoningEffort(): ReasoningEffortState {
  const [effort, setEffortState] = useState<ReasoningLevel | undefined>(undefined);

  // Read after mount so server and first client render agree (no hydration
  // mismatch); the stored choice then applies for the session.
  useEffect(() => {
    setEffortState(readStored());
  }, []);

  const setEffort = useCallback((next: ReasoningLevel | undefined) => {
    setEffortState(next);
    writeStored(next);
  }, []);

  const setIndex = useCallback((index: number) => {
    const option = effortAt(index);
    setEffortState(option.value);
    writeStored(option.value);
  }, []);

  return { effort, index: effortIndex(effort), setIndex, setEffort };
}

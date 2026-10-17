'use client';

// Runtime context for a structured response. The chat wraps each assistant
// message in this provider; a surface that renders without it gets UNAVAILABLE
// for any figure reference (the honest default) and no envelope-state persistence.
//
//   • `figureResolver` — resolves `$ref` figures from the turn's own data.
//   • `stateKey`       — the message id, used to persist envelope-state edits.
//
// `InputsStateProvider` carries the LIVE envelope state to the `inputs` block.

import { createContext, useContext, type ReactNode } from 'react';
import type { FigureResolver } from '@/lib/response/refs';
import type { StateVar } from '@/lib/response/contract';

export interface ResponseRuntime {
  figureResolver: FigureResolver | null;
  stateKey?: string;
}

const ResponseRuntimeContext = createContext<ResponseRuntime>({ figureResolver: null });

export function ResponseRuntimeProvider({
  value,
  children,
}: {
  value: ResponseRuntime;
  children: ReactNode;
}) {
  return <ResponseRuntimeContext.Provider value={value}>{children}</ResponseRuntimeContext.Provider>;
}

export function useResponseRuntime(): ResponseRuntime {
  return useContext(ResponseRuntimeContext);
}

// ── Envelope input state ──────────────────────────────────────────────────────

export interface InputsState {
  vars: StateVar[];
  values: Record<string, number>;
  setValue: (id: string, value: number) => void;
}

const InputsStateContext = createContext<InputsState | null>(null);

export function InputsStateProvider({ value, children }: { value: InputsState; children: ReactNode }) {
  return <InputsStateContext.Provider value={value}>{children}</InputsStateContext.Provider>;
}

export function useInputsState(): InputsState | null {
  return useContext(InputsStateContext);
}

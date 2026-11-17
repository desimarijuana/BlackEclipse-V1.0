'use client';

// ── Studio sidebar ──────────────────────────────────────────────────────────
// The left rail: saved strategies, the thesis/run inputs, the data preflight and
// the project binding. Extracted so the screen stays about the workspace flow.

import React from 'react';
import type { StrategyRecord } from '@/lib/backtest/backtest-client';
import { StrategyLibrary } from './strategy-library';
import { ThesisPanel, type ThesisInputs } from './thesis-panel';
import { DataPreflight } from './data-preflight';
import { ProjectLink } from './project-link';

export function StudioSidebar({
  templates,
  selectedId,
  busy,
  onOpen,
  onNew,
  onTemplate,
  thesis,
  onThesisChange,
  onDraft,
  drafting,
  disabled,
  symbol,
  timeframe,
  saved,
}: {
  templates: Array<{ id: string; name: string; tagline: string }>;
  selectedId: string | null;
  busy: boolean;
  onOpen: (id: string) => void;
  onNew: () => void;
  onTemplate: (id: string) => void;
  thesis: ThesisInputs;
  onThesisChange: (patch: Partial<ThesisInputs>) => void;
  onDraft: () => void;
  drafting: boolean;
  disabled: boolean;
  symbol: string;
  timeframe: string;
  saved: StrategyRecord | null;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <StrategyLibrary
        templates={templates}
        selectedId={selectedId}
        busy={busy}
        onOpen={onOpen}
        onNew={onNew}
        onTemplate={onTemplate}
      />

      <ThesisPanel
        value={thesis}
        onChange={onThesisChange}
        onDraft={onDraft}
        drafting={drafting}
        disabled={disabled}
      />

      <DataPreflight symbolInput={symbol} interval={timeframe} />

      <ProjectLink strategy={saved} />
    </div>
  );
}

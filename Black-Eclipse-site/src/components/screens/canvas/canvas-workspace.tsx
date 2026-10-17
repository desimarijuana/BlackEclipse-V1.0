'use client';

// ─── Canvas workspace (presentation) ──────────────────────────────────────────
// Assembles the three regions from props only. Holds no data logic, so every
// state (empty, loading, error, loaded) is renderable and testable in isolation.

import type { ReactNode } from 'react';
import { AlertTriangle, FileJson, FileText, Loader2, Redo2, SquareCode } from '@/lib/icons';
import type { CanvasKind } from '@/lib/harness/canvas-client';
import { CanvasAiPanel, type CanvasAiPanelProps } from './canvas-ai-panel';
import { CanvasCenter, type CanvasCenterProps } from './canvas-center';
import { CanvasRail, type CanvasRailProps } from './canvas-rail';
import type { CanvasErrorState } from './canvas-utils';

export interface CanvasWorkspaceProps {
  rail: CanvasRailProps;
  center: CanvasCenterProps | null;
  ai: CanvasAiPanelProps;
  loadingArtifact: boolean;
  artifactError: CanvasErrorState | null;
  onRetryArtifact: () => void;
  onCreate: (kind: CanvasKind) => void;
}

function EmptyState({ onCreate }: { onCreate: (kind: CanvasKind) => void }) {
  const actions: { kind: CanvasKind; label: string; icon: ReactNode }[] = [
    { kind: 'document', label: 'New Document', icon: <FileText className="h-4 w-4" /> },
    { kind: 'code', label: 'New Code', icon: <SquareCode className="h-4 w-4" /> },
    { kind: 'visual', label: 'New Visual Report', icon: <FileJson className="h-4 w-4" /> },
  ];
  return (
    <section className="flex min-h-0 flex-1 items-center justify-center">
      <div className="glass-card flex max-w-md flex-col items-center gap-4 rounded-2xl p-8 text-center">
        <div>
          <h2 className="text-lg font-semibold text-foreground">Eclipse Canvas</h2>
          <p className="mt-1 text-sm text-muted-foreground/70">
            Create a document, code artifact or visual report to start editing.
          </p>
        </div>
        <div className="flex flex-wrap justify-center gap-2">
          {actions.map((action) => (
            <button
              key={action.kind}
              type="button"
              onClick={() => onCreate(action.kind)}
              className="glass-button flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm text-foreground"
            >
              {action.icon}
              {action.label}
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}

function ArtifactError({ error, onRetry }: { error: CanvasErrorState; onRetry: () => void }) {
  return (
    <section className="flex min-h-0 flex-1 items-center justify-center" role="alert">
      <div className="glass-card flex max-w-md flex-col items-center gap-3 rounded-2xl p-8 text-center">
        <AlertTriangle className="h-7 w-7 text-rose-400" />
        <p className="text-sm text-rose-200">{error.message}</p>
        {error.status ? <p className="text-[11px] text-muted-foreground/60">Status {error.status}</p> : null}
        <button
          type="button"
          onClick={onRetry}
          className="glass-button flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm text-foreground"
        >
          <Redo2 className="h-3.5 w-3.5" /> Retry
        </button>
      </div>
    </section>
  );
}

export function CanvasWorkspace({
  rail, center, ai, loadingArtifact, artifactError, onRetryArtifact, onCreate,
}: CanvasWorkspaceProps) {
  const fullWidth = center?.fullWidth ?? false;
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 lg:flex-row">
      <CanvasRail {...rail} />
      <main className="flex min-h-0 min-w-0 flex-1 flex-col gap-3">
        {loadingArtifact ? (
          <div className="flex flex-1 items-center justify-center gap-2 text-sm text-muted-foreground/70">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading artifact…
          </div>
        ) : artifactError ? (
          <ArtifactError error={artifactError} onRetry={onRetryArtifact} />
        ) : center ? (
          <CanvasCenter {...center} />
        ) : (
          <EmptyState onCreate={onCreate} />
        )}
      </main>
      {!fullWidth ? <CanvasAiPanel {...ai} /> : null}
    </div>
  );
}

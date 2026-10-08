'use client';

// ── Agent Workspace — Artifacts panel ──────────────────────────────────────────
// Every large output or produced file the run generated, as a compact list that
// opens in the shared Viewer. Never inlines content — only name/type/size.

import { FileJson, FileText, Sparkles } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n';
import type { ArtifactRef } from '@/lib/agent-workspace/types';
import { formatBytes } from '@/lib/agent-workspace/format';

function ArtifactIcon({ type }: { type: ArtifactRef['type'] }) {
  if (type === 'json') return <FileJson size={12} />;
  if (type === 'terminal' || type === 'log') return <FileText size={12} />;
  return <Sparkles size={12} />;
}

export function ArtifactsPanel({
  artifacts,
  onOpen,
}: {
  artifacts: ArtifactRef[];
  onOpen: (artifact: ArtifactRef) => void;
}) {
  const t = useT();
  if (artifacts.length === 0) {
    return <p className="px-1 py-3 text-[12px] text-muted-foreground/50">{t('workspace.empty')}</p>;
  }
  return (
    <ul className="space-y-0.5">
      {artifacts.map((artifact) => (
        <li key={artifact.id}>
          <button
            type="button"
            onClick={() => onOpen(artifact)}
            className={cn(
              'flex w-full items-center gap-2 rounded-lg px-2 py-1 text-left text-[12px]',
              'cursor-pointer hover:bg-accent/40',
            )}
            title={artifact.name}
          >
            <ArtifactIcon type={artifact.type} />
            <span className="min-w-0 flex-1 truncate text-foreground/85">{artifact.name}</span>
            <span className="shrink-0 text-[10px] uppercase tracking-wide text-muted-foreground/40">{artifact.type}</span>
            {artifact.sizeBytes != null && (
              <span className="shrink-0 font-mono text-[10px] tabular-nums text-muted-foreground/50">{formatBytes(artifact.sizeBytes)}</span>
            )}
          </button>
        </li>
      ))}
    </ul>
  );
}

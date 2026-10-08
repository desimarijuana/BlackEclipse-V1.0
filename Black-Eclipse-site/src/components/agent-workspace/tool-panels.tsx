'use client';

// ── Agent Workspace — tool-specific panels (research / browser / computer) ────
// Compact, honest readouts of the three long-running subsystems the runtime
// already owns. They NEVER create a second browser/computer/research system —
// they only reflect the events the runtime emits. Coordinates, screenshots and
// costs appear only when the runtime actually provides them.

import { Globe, Image as ImageIcon, Monitor, FlaskConical } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n';
import type { BrowserState, ComputerState, ResearchState } from '@/lib/agent-workspace/types';
import { StatTile } from './ui';

function ActiveBadge({ active }: { active: boolean }) {
  const t = useT();
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] uppercase tracking-wide',
        active ? 'border-primary/30 bg-primary/10 text-primary' : 'border-white/10 text-muted-foreground/60',
      )}
    >
      <span className={cn('h-1.5 w-1.5 rounded-full', active ? 'bg-primary' : 'bg-muted-foreground/40')} />
      {active ? t('workspace.status.running') : t('workspace.status.idle')}
    </span>
  );
}

export function ResearchPanel({ research }: { research?: ResearchState }) {
  const t = useT();
  if (!research || (!research.active && research.sources === 0 && research.queries === 0)) {
    return <p className="px-1 py-3 text-[12px] text-muted-foreground/50">{t('workspace.empty')}</p>;
  }
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground/70">
          <FlaskConical size={13} /> {t('workspace.panel.research')}
        </span>
        <ActiveBadge active={research.active} />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <StatTile label={t('workspace.queries')} value={research.queries > 0 ? research.queries : undefined} unavailable={t('workspace.notAvailable')} />
        <StatTile label={t('workspace.sources')} value={research.sources > 0 ? research.sources : undefined} unavailable={t('workspace.notAvailable')} />
        <StatTile label={t('workspace.claims')} value={research.claims > 0 ? research.claims : undefined} unavailable={t('workspace.notAvailable')} />
        <StatTile label={t('workspace.conflicts')} value={research.conflicts > 0 ? research.conflicts : undefined} unavailable={t('workspace.notAvailable')} tone={research.conflicts > 0 ? 'failed' : 'default'} />
      </div>
      {research.coverage && (
        <p className="px-0.5 text-[11px] text-muted-foreground/60">
          {t('workspace.coverage')}: <span className="text-foreground/80">{research.coverage}</span>
        </p>
      )}
    </div>
  );
}

export function BrowserPanel({ browser }: { browser?: BrowserState }) {
  const t = useT();
  if (!browser || (!browser.active && browser.actions === 0)) {
    return <p className="px-1 py-3 text-[12px] text-muted-foreground/50">{t('workspace.empty')}</p>;
  }
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground/70">
          <Globe size={13} /> {t('workspace.panel.browser')}
        </span>
        <ActiveBadge active={browser.active} />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <StatTile label={t('workspace.actions')} value={browser.actions > 0 ? browser.actions : undefined} unavailable={t('workspace.notAvailable')} />
        <StatTile label={t('workspace.lastAction')} value={browser.lastAction} unavailable={t('workspace.notAvailable')} />
      </div>
      <div className="rounded-xl border border-white/8 bg-white/[0.03] px-3 py-2">
        <div className="text-[10px] uppercase tracking-wide text-muted-foreground/60">{t('workspace.activeUrl')}</div>
        <div className="mt-0.5 truncate font-mono text-[11px] text-foreground/80" title={browser.url}>
          {browser.url ?? t('workspace.notAvailable')}
        </div>
        {browser.sessionId && <div className="mt-0.5 truncate font-mono text-[10px] text-muted-foreground/40">{browser.sessionId}</div>}
      </div>
      {browser.screenshotRef ? (
        <div className="flex items-center gap-2 rounded-xl border border-white/8 bg-white/[0.03] px-3 py-2 text-[11px] text-muted-foreground/70">
          <ImageIcon size={13} /> {t('workspace.latestScreenshot')}
          <span className="min-w-0 flex-1 truncate font-mono text-[10px] text-muted-foreground/40">{browser.screenshotRef}</span>
        </div>
      ) : (
        <p className="px-0.5 text-[11px] text-muted-foreground/50">{t('workspace.notAvailable')}</p>
      )}
    </div>
  );
}

export function ComputerPanel({ computer }: { computer?: ComputerState }) {
  const t = useT();
  if (!computer || (!computer.active && computer.actions === 0)) {
    return <p className="px-1 py-3 text-[12px] text-muted-foreground/50">{t('workspace.empty')}</p>;
  }
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground/70">
          <Monitor size={13} /> {t('workspace.panel.computer')}
        </span>
        <ActiveBadge active={computer.active} />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <StatTile label={t('workspace.application')} value={computer.application} unavailable={t('workspace.notAvailable')} />
        <StatTile label={t('workspace.actions')} value={computer.actions > 0 ? computer.actions : undefined} unavailable={t('workspace.notAvailable')} />
        <StatTile label={t('workspace.lastAction')} value={computer.lastAction} unavailable={t('workspace.notAvailable')} />
      </div>
      {computer.screenshotRef && (
        <div className="flex items-center gap-2 rounded-xl border border-white/8 bg-white/[0.03] px-3 py-2 text-[11px] text-muted-foreground/70">
          <ImageIcon size={13} /> {t('workspace.latestScreenshot')}
          <span className="min-w-0 flex-1 truncate font-mono text-[10px] text-muted-foreground/40">{computer.screenshotRef}</span>
        </div>
      )}
    </div>
  );
}

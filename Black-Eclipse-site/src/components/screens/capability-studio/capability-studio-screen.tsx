'use client';

// ── Capability Studio ───────────────────────────────────────────────────────
// ONE navigable surface for everything Eclipse can be extended with: pages &
// widgets (the UI Builder), tools & plugins, skills, and the operator's
// connected data (integrations). It is a navigation shell over the EXISTING
// managers — each section mounts or links the manager that already owns its
// lifecycle — so there is no second registry, no duplicated enable path, and
// nothing here grants itself anything: plugin enable/disable runs the plugin
// platform's own operator action, skill enable stays in the evaluation- and
// promotion-gated Skills manager, and connections stay in Settings.
//
// The tab id stays `ui-builder` (deep links, search destinations and the shell
// keep working); `?tab=ui-builder&sub=studio.<section>` opens a section.

import { useCallback, useState } from 'react';
import { Blocks, Globe, LayoutGrid, Plug } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n/use-t';
import { useSubroute } from '@/hooks/use-subroute';
import { useCommandStore } from '@/lib/search/store';
import { UiBuilderScreen } from '@/components/screens/ui-builder/ui-builder-screen';
import { PluginsScreen } from '@/components/screens/plugins/plugins-screen';
import { SkillsSection } from './skills-section';
import { IntegrationsSection } from './integrations-section';

export type StudioSection = 'pages' | 'plugins' | 'skills' | 'integrations';

const SECTIONS: readonly StudioSection[] = ['pages', 'plugins', 'skills', 'integrations'];

const SECTION_LABEL = {
  pages: 'studio.section.pages',
  plugins: 'studio.section.plugins',
  skills: 'studio.section.skills',
  integrations: 'studio.section.integrations',
} as const satisfies Record<StudioSection, string>;

const SECTION_ICON = {
  pages: LayoutGrid,
  plugins: Plug,
  skills: Blocks,
  integrations: Globe,
} as const;

export function CapabilityStudioScreen({
  initialSection = 'pages',
}: {
  initialSection?: StudioSection;
} = {}) {
  const t = useT();
  const [section, setSection] = useState<StudioSection>(initialSection);
  // Keep visited sections mounted (display:none on the inactive one), the same
  // pattern the shell uses for tabs: switching to Plugins and back must not
  // drop the builder's selected page or in-flight edit.
  const [visited, setVisited] = useState<ReadonlySet<StudioSection>>(new Set([initialSection]));

  const open = useCallback((next: StudioSection) => {
    setSection(next);
    setVisited((prev) => (prev.has(next) ? prev : new Set([...prev, next])));
  }, []);

  // The shell publishes `?tab=ui-builder&sub=studio.<section>` as `<section>`.
  useSubroute('ui-builder', (req) => {
    if ((SECTIONS as readonly string[]).includes(req.subroute)) {
      open(req.subroute as StudioSection);
    }
  });

  return (
    <div className="flex h-full w-full flex-col gap-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-serif text-2xl font-semibold text-foreground">{t('studio.title')}</h1>
          <p className="max-w-3xl text-xs text-muted-foreground">{t('studio.subtitle')}</p>
        </div>
        <nav aria-label={t('studio.title')} className="glass-card-subtle flex flex-wrap items-center gap-1 rounded-xl border border-border/20 p-1">
          {SECTIONS.map((id) => {
            const Icon = SECTION_ICON[id];
            return (
              <button
                key={id}
                type="button"
                onClick={() => open(id)}
                aria-pressed={section === id}
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs transition-colors',
                  section === id
                    ? 'bg-white/10 font-medium text-foreground'
                    : 'text-muted-foreground hover:bg-white/5 hover:text-foreground',
                )}
              >
                <Icon size={12} />
                {t(SECTION_LABEL[id])}
              </button>
            );
          })}
        </nav>
      </header>

      <div className="min-h-0 flex-1">
        {visited.has('pages') && (
          <div className={cn('h-full w-full', section === 'pages' ? '' : 'hidden')}>
            <UiBuilderScreen embedded />
          </div>
        )}
        {visited.has('plugins') && (
          <div className={cn('h-full w-full', section === 'plugins' ? '' : 'hidden')}>
            <div className="flex h-full flex-col gap-2">
              <p className="text-[11px] text-muted-foreground">{t('studio.plugins.hint')}</p>
              <div className="min-h-0 flex-1">
                <PluginsScreen />
              </div>
            </div>
          </div>
        )}
        {visited.has('skills') && (
          <div className={cn('h-full w-full', section === 'skills' ? '' : 'hidden')}>
            <SkillsSection
              onOpenSkills={() => useCommandStore.getState().dispatch({ tab: 'skills' })}
            />
          </div>
        )}
        {visited.has('integrations') && (
          <div className={cn('h-full w-full', section === 'integrations' ? '' : 'hidden')}>
            <IntegrationsSection
              onOpenSettings={(target) =>
                useCommandStore.getState().dispatch({ tab: 'settings', subroute: `settings.${target}` })
              }
            />
          </div>
        )}
      </div>
    </div>
  );
}

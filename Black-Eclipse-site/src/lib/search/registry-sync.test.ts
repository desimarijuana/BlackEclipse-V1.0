// ─── Registry sync guard ──────────────────────────────────────────────────────
// The palette registry used to drift from the rendered UI (Memory declared 8
// of 16 tabs, Skills missed Maintenance, Journal missed Decisions/Notebook,
// sidebar-visible screens had no page at all). These tests make drift a build
// failure instead of a silent gap:
//
//   1. every AppTab (except the deliberately retired `chart`) has a top-level
//      page entry — users can always navigate to a screen by name;
//   2. every rendered Memory / Skills / Journal tab has a registered sub-page
//      whose title matches the rendered label exactly;
//   3. the economics / discovery / alerts sub-pages match the screens' own
//      rendered tab ids (pinned contract);
//   4. the palette's Pages launcher (LAUNCHER_ORDER) covers every sidebar
//      section plus Bots, and contains only top-level destinations (never the
//      `settings` modal or the retired `chart` tab).

import { describe, expect, it } from 'vitest';

import { APP_TABS } from './deep-link';
import { MEMORY_TABS, SKILLS_TABS } from '@/lib/app-screens';
import { JOURNAL_TABS } from '@/lib/journal-tabs';
import { DEFAULT_SIDEBAR_SECTIONS } from '@/lib/sidebar/config';
import { getAllPages, getLauncherPages, LAUNCHER_ORDER, getPage } from './registry';

const pages = getAllPages();
const topLevelTabs = new Set(pages.filter((p) => !p.destination.subroute).map((p) => p.destination.tab));
const bySubroute = new Map(pages.filter((p) => p.destination.subroute).map((p) => [p.destination.subroute as string, p]));

// The shell rewrites the legacy `graph-studio` tab id to `overview` (same
// screen), and `chart` is deliberately retired — neither is its own palette
// page; both are covered by `page-overview` / by nothing.
const NO_OWN_PAGE: Partial<Record<(typeof APP_TABS)[number], string>> = {
  chart: 'retired tab',
  'graph-studio': 'legacy alias of overview (rewritten by the shell)',
};

describe('registry ↔ app sync', () => {
  it('every tab (except retired `chart` / legacy `graph-studio`) has a top-level page', () => {
    for (const tab of APP_TABS) {
      if (tab in NO_OWN_PAGE) continue;
      expect(topLevelTabs.has(tab), `no palette page for tab "${tab}"`).toBe(true);
    }
  });

  it('every rendered Memory tab is a registered sub-page with the rendered label', () => {
    for (const t of MEMORY_TABS) {
      const sub = bySubroute.get(`memory.${t.id}`);
      expect(sub, `memory.${t.id} missing`).toBeDefined();
      expect(sub?.title).toBe(t.label);
      expect(sub?.destination.tab).toBe('memory');
    }
  });

  it('every rendered Skills tab is a registered sub-page with the rendered label', () => {
    for (const t of SKILLS_TABS) {
      const sub = bySubroute.get(`skills.${t.id}`);
      expect(sub, `skills.${t.id} missing`).toBeDefined();
      expect(sub?.title).toBe(t.label);
      expect(sub?.destination.tab).toBe('skills');
    }
  });

  it('every rendered Journal tab is a registered sub-page with the rendered label', () => {
    for (const t of JOURNAL_TABS) {
      const sub = bySubroute.get(`journal.${t.id}`);
      expect(sub, `journal.${t.id} missing`).toBeDefined();
      expect(sub?.title).toBe(t.label);
      expect(sub?.destination.tab).toBe('journal');
    }
  });

  it('economics / discovery / alerts sub-pages match the screens’ rendered ids', () => {
    for (const slug of [
      'economics.overview', 'economics.calendar', 'economics.explorer',
      'discovery.markets', 'discovery.stocks', 'discovery.etfs', 'discovery.funds',
      'discovery.dividend_stocks', 'discovery.crypto', 'discovery.forex', 'discovery.commodities',
      'alerts.watches', 'alerts.create', 'alerts.history',
    ]) {
      expect(bySubroute.has(slug), `${slug} missing`).toBe(true);
    }
  });

  it('launcher covers every sidebar section plus Bots', () => {
    const launcher = getLauncherPages();
    for (const section of DEFAULT_SIDEBAR_SECTIONS) {
      expect(
        launcher.some((p) => p.destination.tab === section.id),
        `launcher missing sidebar section "${section.id}"`,
      ).toBe(true);
    }
    expect(launcher.some((p) => p.destination.tab === 'bots')).toBe(true);
  });

  it('launcher contains only resolvable, top-level, non-modal destinations', () => {
    for (const id of LAUNCHER_ORDER) {
      const page = getPage(id);
      expect(page, `launcher id "${id}" is not registered`).toBeDefined();
      expect(page?.destination.subroute, `launcher id "${id}" is a sub-page`).toBeUndefined();
      expect(['settings', 'chart']).not.toContain(page?.destination.tab);
    }
    const launcher = getLauncherPages();
    expect(new Set(launcher.map((p) => p.id)).size).toBe(launcher.length);
  });

  it('no sub-page is flagged as a top-level launcher row', () => {
    for (const page of pages) {
      if (page.destination.subroute) {
        expect(LAUNCHER_ORDER).not.toContain(page.id);
      }
    }
  });
});

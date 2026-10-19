// ── App surfaces — the app's own screen inventory ──────────────────────────
// `ui_get_application_map` used to list only the user's saved dashboard
// blueprints. The runtime had no vocabulary for the app's FIXED screens and
// sub-tabs, so an agent asked "does Memory → Reviews exist?" answered no.
//
// This module derives the inventory from the existing single sources:
//   * `app-tabs.ts`        — the exhaustive AppTab union (every screen);
//   * `app-screens.ts`     — the RENDERED tab bars for screens whose palette
//                            registry entry drifted (Memory, Skills);
//   * `search/registry.ts` — registered sub-tabs for every other screen;
//   * `search/deep-link.ts`— the canonical `/?tab=…&sub=…` href form;
//   * `sidebar/config.ts`  — the label for tabs without a search page.

import type { AppTab } from './app-tabs';
import { APP_SCREENS } from './app-screens';
import { APP_TABS, destinationToHref } from './search/deep-link';
import { getAllPages } from './search/registry';
import { DEFAULT_SIDEBAR_SECTIONS } from './sidebar/config';

export interface AppSurfaceTab {
  id: string;
  label: string;
  deepLink: string;
}

export interface AppSurface {
  id: AppTab;
  label: string;
  deepLink: string;
  tabs: AppSurfaceTab[];
}

function humanize(tab: string): string {
  return tab
    .split('-')
    .filter(Boolean)
    .map((word) => word[0].toUpperCase() + word.slice(1))
    .join(' ');
}

/** Every app screen with its sub-tabs and deep links, in AppTab order. */
export function appSurfaces(): AppSurface[] {
  const pages = getAllPages();
  const sidebarLabels = new Map(DEFAULT_SIDEBAR_SECTIONS.map((s) => [s.id, s.label] as const));
  const screenDefs = new Map(APP_SCREENS.map((s) => [s.id, s] as const));
  return APP_TABS.map((tab) => {
    const screen = screenDefs.get(tab);
    if (screen) {
      return {
        id: tab,
        label: screen.label,
        deepLink: destinationToHref({ tab }),
        tabs: screen.tabs.map((sub) => ({
          id: `${tab}.${sub.id}`,
          label: sub.label,
          deepLink: destinationToHref({ tab, subroute: `${tab}.${sub.id}` }),
        })),
      };
    }
    const topLevel = pages.find(
      (p) => p.destination.tab === tab && !p.destination.subroute && !p.destination.params,
    );
    const tabs = pages
      .filter((p) => p.destination.tab === tab && Boolean(p.destination.subroute))
      .map((p) => ({
        id: p.destination.subroute as string,
        label: p.title,
        deepLink: destinationToHref({ tab, subroute: p.destination.subroute }),
      }));
    return {
      id: tab,
      label: topLevel?.title ?? sidebarLabels.get(tab) ?? humanize(tab),
      deepLink: destinationToHref({ tab }),
      tabs,
    };
  });
}

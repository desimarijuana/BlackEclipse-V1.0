import { describe, expect, it } from 'vitest';
import {
  DASHBOARD_TEMPLATES,
  TEMPLATE_WIDGET_IDS,
} from '@/lib/dashboard/templates';
import { ASSET_RAIL, LEFT_WIDGET_IDS } from '@/lib/dashboard/layout';
import {
  buildDashboardTemplateLayout,
  buildDefaultDashboardLayout,
  listDashboardTemplates,
} from './dashboard-templates';

function idsIn(layout: ReturnType<typeof buildDashboardTemplateLayout>): string[] {
  return layout.sections.flatMap((section) =>
    section.columns.flatMap((column) => column.widgets.map((widget) => widget.widgetId)),
  );
}

function zoneIds(layout: ReturnType<typeof buildDashboardTemplateLayout>, zone: string): string[] {
  return layout.sections
    .filter((section) => (section.zone ?? 'main') === zone)
    .flatMap((section) => section.columns.flatMap((column) => column.widgets.map((widget) => widget.widgetId)));
}

describe('dashboard template SDK surface', () => {
  it('lists every persona from the ONE TS registry', () => {
    const listed = listDashboardTemplates();
    expect(listed.map((template) => template.id)).toEqual(DASHBOARD_TEMPLATES.map((template) => template.id));
    expect(listed.find((template) => template.id === 'rates-desk')?.name).toBe('Rates Desk');
  });

  it('builds a full board with centre bands and both side rails', () => {
    for (const template of DASHBOARD_TEMPLATES) {
      const layout = buildDashboardTemplateLayout(template.id, { market: 'US' });
      expect(idsIn(layout).length).toBeGreaterThan(0);
      expect(zoneIds(layout, 'main').length).toBeGreaterThan(0);
      expect(zoneIds(layout, 'left')).toEqual([...LEFT_WIDGET_IDS]);
      expect(zoneIds(layout, 'right')).toEqual([...ASSET_RAIL.equity]);
    }
  });

  it('never places the same widget twice', () => {
    for (const template of DASHBOARD_TEMPLATES) {
      const used = idsIn(buildDashboardTemplateLayout(template.id));
      expect(new Set(used).size).toBe(used.length);
    }
  });

  it('uses the market asset class for the right rail', () => {
    expect(zoneIds(buildDashboardTemplateLayout('tape-reader', { market: 'FOREX' }), 'right'))
      .toEqual([...ASSET_RAIL.forex]);
    expect(zoneIds(buildDashboardTemplateLayout('tape-reader', { market: 'CRYPTO' }), 'right'))
      .toEqual([...ASSET_RAIL.crypto]);
  });

  it('resolves legacy template ids but rejects a genuinely unknown one', () => {
    expect(idsIn(buildDashboardTemplateLayout('macro')).length).toBeGreaterThan(0);
    expect(() => buildDashboardTemplateLayout('does-not-exist')).toThrow(/unknown dashboard template/);
  });

  it('resets to a non-empty default board', () => {
    const layout = buildDefaultDashboardLayout({ market: 'US' });
    expect(idsIn(layout).length).toBeGreaterThan(0);
    expect(zoneIds(layout, 'left')).toEqual([...LEFT_WIDGET_IDS]);
  });

  it('keeps the server-safe widget list in sync with every template', () => {
    for (const template of DASHBOARD_TEMPLATES) {
      const built = template.build(TEMPLATE_WIDGET_IDS);
      expect(idsIn(built).length).toBeGreaterThan(0);
      for (const id of idsIn(built)) expect(TEMPLATE_WIDGET_IDS).toContain(id);
    }
  });
});

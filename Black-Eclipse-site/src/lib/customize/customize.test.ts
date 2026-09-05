import { describe, it, expect } from 'vitest';
import {
  defaultLayout, layoutFromPreset, migrateV1toV2, normalizeLayout, newSectionId,
  type PageDefinition, type PageLayoutV1,
} from './types';
import { patched, placeWidget, setSectionColumns, addWidget, removeWidget, nudged, loadLayout } from './layout';

const DEF: PageDefinition = {
  pageId: 'test',
  storageKey: 'eclipse_test_layout',
  widgets: {
    a: { label: 'A', defaultSpan: 4 },
    b: { label: 'B', defaultSpan: 2 },
    c: { label: 'C', defaultSpan: 2 },
    d: { label: 'D', defaultSpan: 1 },
    e: { label: 'E', defaultSpan: 1 },
  },
  presets: [
    { id: 'p1', name: 'P1', desc: '', preview: [], sections: [[2, 'a'], [2, 'b', 'c'], [4, 'd', 'e']] },
  ],
};

describe('customize kernel — v2 schema', () => {
  it('builds a default layout grouping widgets by span', () => {
    const l = defaultLayout(DEF);
    expect(l.version).toBe(2);
    // a(4) → 1-col; b,c(2) → 2-col; d,e(1) → 4-col
    expect(l.sections.map((s) => s.columns)).toEqual([1, 2, 4]);
    expect(l.sections.flatMap((s) => s.widgets.map((w) => w.id))).toEqual(['a', 'b', 'c', 'd', 'e']);
  });

  it('builds a preset into sections with a trailing overflow section', () => {
    const l = layoutFromPreset(DEF, DEF.presets[0]);
    expect(l.sections.map((s) => s.columns)).toEqual([2, 2, 4]);
    // All widgets placed, none left over
    expect(l.sections.flatMap((s) => s.widgets.map((w) => w.id))).toEqual(['a', 'b', 'c', 'd', 'e']);
  });

  it('migrates v1 flat layouts (run-length grouping by span)', () => {
    const v1: PageLayoutV1 = {
      version: 1,
      widgets: [
        { id: 'a', visible: true, span: 4 },
        { id: 'b', visible: true, span: 2 },
        { id: 'c', visible: true, span: 2 },
        { id: 'd', visible: true, span: 1 },
        { id: 'e', visible: true, span: 1 },
      ],
    };
    const l = migrateV1toV2(v1);
    expect(l.version).toBe(2);
    expect(l.sections.map((s) => s.columns)).toEqual([1, 2, 4]);
    expect(l.sections.every((s) => s.id.startsWith('sec-'))).toBe(true);
  });

  it('normalizeLayout upgrades stored v1 and appends unknown widgets', () => {
    const stored = { version: 1, widgets: [{ id: 'a', visible: true, span: 4 }] };
    const l = normalizeLayout(DEF, stored);
    expect(l.version).toBe(2);
    const ids = l.sections.flatMap((s) => s.widgets.map((w) => w.id));
    expect(ids).toContain('a');
    // b–e were never in storage → appended
    for (const id of ['b', 'c', 'd', 'e']) expect(ids).toContain(id);
  });

  it('normalizeLayout validates v2 sections and drops unknown widget ids', () => {
    const stored = {
      version: 2,
      sections: [
        { id: 's1', columns: 2, widgets: [{ id: 'a', visible: true, height: 0 }, { id: 'zzz', visible: true, height: 0 }] },
      ],
    };
    const l = normalizeLayout(DEF, stored);
    // s1 kept (unknown widget dropped) + one overflow section with b–e
    expect(l.sections).toHaveLength(2);
    expect(l.sections[0].widgets.map((w) => w.id)).toEqual(['a']);
    // Rest appended
    expect(l.sections[1].widgets.map((w) => w.id).sort()).toEqual(['b', 'c', 'd', 'e']);
  });

  it('setSectionColumns reflows overflow into a new section', () => {
    let l = layoutFromPreset(DEF, DEF.presets[0]); // [a] [b c] [d e]
    const sec2 = l.sections[1];
    l = setSectionColumns(l, sec2.id, 1);
    expect(l.sections[1].columns).toBe(1);
    expect(l.sections[1].widgets.map((w) => w.id)).toEqual(['b']);
    expect(l.sections[2].widgets.map((w) => w.id)).toEqual(['c']);
  });

  it('placeWidget moves across sections', () => {
    let l = layoutFromPreset(DEF, DEF.presets[0]); // [a] [b c] [d e]
    l = placeWidget(l, 'c', l.sections[0].id, null);
    expect(l.sections[0].widgets.map((w) => w.id)).toEqual(['a', 'c']);
    // 'b' remains in its own section; 'd','e' untouched
    expect(l.sections).toHaveLength(3);
    expect(l.sections[1].widgets.map((w) => w.id)).toEqual(['b']);
  });

  it('placeWidget prunes a section emptied by the move', () => {
    let l = layoutFromPreset(DEF, DEF.presets[0]); // [a] [b c] [d e]
    // Move b into section 3, then c into section 3 — section 2 empties
    l = placeWidget(l, 'b', l.sections[2].id, null);
    l = placeWidget(l, 'c', l.sections[2].id, null);
    expect(l.sections).toHaveLength(2);
    expect(l.sections[1].widgets.map((w) => w.id)).toEqual(['d', 'e', 'b', 'c']);
  });

  it('patch toggles visibility anywhere in the tree', () => {
    let l = layoutFromPreset(DEF, DEF.presets[0]);
    l = patched(l, 'd', { visible: false });
    expect(l.sections[2].widgets[0].visible).toBe(false);
  });

  it('addWidget + removeWidget round-trip through hidden library', () => {
    let l = layoutFromPreset(DEF, DEF.presets[0]);
    l = removeWidget(l, 'b');
    expect(l.sections.flatMap((s) => s.widgets.map((w) => w.id))).not.toContain('b');
    l = addWidget(l, DEF, 'b', l.sections[0].id);
    expect(l.sections[0].widgets.map((w) => w.id)).toEqual(['a', 'b']);
  });

  it('nudge swaps within a section only', () => {
    let l = layoutFromPreset(DEF, DEF.presets[0]);
    l = nudged(l, 'c', -1); // c before b
    expect(l.sections[1].widgets.map((w) => w.id)).toEqual(['c', 'b']);
    l = nudged(l, 'c', 1);
    expect(l.sections[1].widgets.map((w) => w.id)).toEqual(['b', 'c']);
  });

  it('loadLayout falls back to defaults on garbage', () => {
    // No window in test env → default branch
    const l = loadLayout(DEF);
    expect(l.version).toBe(2);
    expect(l.sections.length).toBeGreaterThan(0);
  });

  it('newSectionId is unique', () => {
    expect(newSectionId()).not.toBe(newSectionId());
  });
});
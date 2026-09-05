import { describe, it, expect } from 'vitest';
import {
  defaultLayout, layoutFromPreset, migrateV1toV3, migrateV2toV3, normalizeLayout,
  newSectionId, allElementIds, type PageDefinition, type PageLayoutV1, type PageLayoutV2, type PageLayout, type Section,
} from './types';
import {
  patched, placeElement, setColumnCount, setColumnWidth, addElement, removeElement,
  nudged, loadLayout, patchSection, 
} from './layout';

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
    { id: 'p1', name: 'P1', desc: '', preview: [], sections: [
      { widths: [1], elements: ['a'] },
      { widths: [1, 1], elements: ['b', 'c'] },
      { widths: [1, 1, 1, 1], elements: ['d', 'e'] },
    ] },
  ],
};

/** Re-find a section by id in the CURRENT layout (ops clone the tree). */
function sec(l: PageLayout, id: string): Section {
  const s = l.sections.find((x) => x.id === id);
  if (!s) throw new Error(`section ${id} not found`);
  return s;
}

describe('customize kernel — v3 section → column → element', () => {
  it('builds a default layout: one section per defaultSpan group', () => {
    const l = defaultLayout(DEF);
    expect(l.version).toBe(3);
    expect(l.sections).toHaveLength(3);
    expect(allElementIds(l)).toEqual(['a', 'b', 'c', 'd', 'e']);
    expect(l.sections[0].columns).toHaveLength(1);
    expect(l.sections[1].columns).toHaveLength(2);
    expect(l.sections[2].columns).toHaveLength(2); // d,e share a 4-capacity section
  });

  it('preset: one column per width entry; elements distributed', () => {
    const l = layoutFromPreset(DEF, DEF.presets[0]);
    expect(allElementIds(l)).toEqual(['a', 'b', 'c', 'd', 'e']);
    const s2 = l.sections[1];
    expect(s2.columns).toHaveLength(2);
    expect(s2.columns[0].elements.map((e) => e.id)).toEqual(['b']);
    expect(s2.columns[1].elements.map((e) => e.id)).toEqual(['c']);
  });

  it('elements stack inside a column (many per column)', () => {
    let l = layoutFromPreset(DEF, DEF.presets[0]);
    const sec2Id = l.sections[1].id;
    const col0 = l.sections[1].columns[0].id;
    l = placeElement(l, 'c', { sectionId: sec2Id, columnId: col0, elementIdx: null });
    const s2 = sec(l, sec2Id);
    expect(s2.columns[0].elements.map((e) => e.id)).toEqual(['b', 'c']);
    // Emptied source column auto-pruned
    expect(s2.columns).toHaveLength(1);
  });

  it('placeElement inserts at a precise element index', () => {
    let l = layoutFromPreset(DEF, DEF.presets[0]);
    const sec2Id = l.sections[1].id;
    const col0 = l.sections[1].columns[0].id;
    l = placeElement(l, 'c', { sectionId: sec2Id, columnId: col0, elementIdx: 0 });
    expect(sec(l, sec2Id).columns[0].elements.map((e) => e.id)).toEqual(['c', 'b']);
  });

  it('placeElement moves across sections and prunes emptied columns', () => {
    let l = layoutFromPreset(DEF, DEF.presets[0]);
    const sec2Id = l.sections[1].id;
    const sec3Id = l.sections[2].id;
    const sec3col0 = l.sections[2].columns[0].id;
    l = placeElement(l, 'b', { sectionId: sec3Id, columnId: sec3col0, elementIdx: null });
    const s2 = sec(l, sec2Id);
    expect(s2.columns).toHaveLength(1);
    expect(s2.columns[0].elements.map((e) => e.id)).toEqual(['c']);
    expect(sec(l, sec3Id).columns[0].elements.map((e) => e.id)).toContain('b');
  });

  it('setColumnCount redistributes elements row-major', () => {
    let l = layoutFromPreset(DEF, DEF.presets[0]);
    const sec2Id = l.sections[1].id;
    l = setColumnCount(l, sec2Id, 1);
    let s2 = sec(l, sec2Id);
    expect(s2.columns).toHaveLength(1);
    expect(s2.columns[0].elements.map((e) => e.id)).toEqual(['b', 'c']);
    l = setColumnCount(l, sec2Id, 2);
    s2 = sec(l, sec2Id);
    expect(s2.columns[0].elements.map((e) => e.id)).toEqual(['b']);
    expect(s2.columns[1].elements.map((e) => e.id)).toEqual(['c']);
  });

  it('setColumnWidth changes only the target column', () => {
    let l = layoutFromPreset(DEF, DEF.presets[0]);
    const sec2Id = l.sections[1].id;
    const col0 = l.sections[1].columns[0].id;
    l = setColumnWidth(l, col0, 3);
    const s2 = sec(l, sec2Id);
    expect(s2.columns[0].width).toBe(3);
    expect(s2.columns[1].width).toBe(1);
  });

  it('patched sets element style + visibility independently of layout', () => {
    let l = layoutFromPreset(DEF, DEF.presets[0]);
    l = patched(l, 'b', { style: { height: 3, padding: 'md', align: 'center' }, visible: false });
    const b = l.sections[1].columns[0].elements[0];
    expect(b.style.height).toBe(3);
    expect(b.style.padding).toBe('md');
    expect(b.style.align).toBe('center');
    expect(b.visible).toBe(false);
    expect(l.sections[1].columns[1].elements[0].visible).toBe(true);
  });

  it('patchSection sets gap/padding without touching elements', () => {
    let l = layoutFromPreset(DEF, DEF.presets[0]);
    const sec1Id = l.sections[0].id;
    l = patchSection(l, sec1Id, { gap: 24, padding: 'sm' });
    expect(sec(l, sec1Id).gap).toBe(24);
    expect(sec(l, sec1Id).padding).toBe('sm');
    expect(allElementIds(l)).toEqual(['a', 'b', 'c', 'd', 'e']);
  });

  it('nudge reorders within a column, then spills to the neighbour', () => {
    let l = layoutFromPreset(DEF, DEF.presets[0]);
    const sec2Id = l.sections[1].id;
    const col0 = l.sections[1].columns[0].id;
    l = placeElement(l, 'c', { sectionId: sec2Id, columnId: col0, elementIdx: null });
    l = nudged(l, 'c', -1);
    expect(sec(l, sec2Id).columns[0].elements.map((e) => e.id)).toEqual(['c', 'b']);
  });

  it('addElement puts a library widget into a column or new section', () => {
    let l = layoutFromPreset(DEF, DEF.presets[0]);
    l = removeElement(l, 'e');
    expect(allElementIds(l)).not.toContain('e');
    const sec1Id = l.sections[0].id;
    const col0 = l.sections[0].columns[0].id;
    l = addElement(l, DEF, 'e', col0);
    expect(sec(l, sec1Id).columns[0].elements.map((e) => e.id)).toEqual(['a', 'e']);
    const before = allElementIds(l);
    l = addElement(l, DEF, 'e', null);
    expect(allElementIds(l)).toEqual(before);
  });

  it('migrates v1 flat layouts', () => {
    const v1: PageLayoutV1 = {
      version: 1,
      widgets: [
        { id: 'a', visible: true, span: 4 },
        { id: 'b', visible: true, span: 2 },
        { id: 'c', visible: true, span: 2 },
      ],
    };
    const l = migrateV1toV3(v1);
    expect(l.version).toBe(3);
    expect(allElementIds(l)).toEqual(['a', 'b', 'c']);
  });

  it('migrates v2 sections (one widget per slot)', () => {
    const v2: PageLayoutV2 = {
      version: 2,
      sections: [
        { columns: 2, widgets: [{ id: 'b', visible: true, height: 0 }, { id: 'c', visible: true, height: 0 }] },
      ],
    };
    const l = migrateV2toV3(v2);
    expect(allElementIds(l)).toEqual(['b', 'c']);
    expect(l.sections[0].columns).toHaveLength(2);
  });

  it('normalizeLayout handles v1, v2, v3 and appends unknown widgets', () => {
    const l1 = normalizeLayout(DEF, { version: 1, widgets: [{ id: 'a', visible: true, span: 4 }] });
    expect(allElementIds(l1)).toContain('a');
    for (const id of ['b', 'c', 'd', 'e']) expect(allElementIds(l1)).toContain(id);

    const l2 = normalizeLayout(DEF, { version: 2, sections: [{ columns: 2, widgets: [{ id: 'b', visible: true }] }] });
    expect(allElementIds(l2)).toContain('b');

    const l3 = normalizeLayout(DEF, {
      version: 3,
      sections: [{ id: 's1', gap: 16, padding: 'none', columns: [{ id: 'c1', width: 1, elements: [{ id: 'a', visible: true, style: { height: 2, width: 'auto', padding: 'none', align: 'stretch' } }] }] }],
    });
    expect(allElementIds(l3)).toContain('a');
    expect(l3.sections[0].columns[0].elements[0].style.height).toBe(2);

    const l4 = normalizeLayout(DEF, { version: 3, sections: [{ id: 's1', gap: 16, padding: 'none', columns: [{ id: 'c1', width: 1, elements: [{ id: 'zzz', visible: true, style: { height: 0, width: 'auto', padding: 'none', align: 'stretch' } }] }] }] });
    expect(allElementIds(l4)).not.toContain('zzz');
    expect(allElementIds(l4)).toEqual(['a', 'b', 'c', 'd', 'e']);
  });

  it('loadLayout falls back to defaults without window', () => {
    const l = loadLayout(DEF);
    expect(l.version).toBe(3);
    expect(l.sections.length).toBeGreaterThan(0);
  });

  it('newSectionId is unique', () => {
    expect(newSectionId()).not.toBe(newSectionId());
  });
});
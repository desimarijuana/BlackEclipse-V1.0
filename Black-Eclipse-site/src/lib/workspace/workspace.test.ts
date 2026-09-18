import { describe, expect, it } from 'vitest';
import { produce } from 'immer';
import {
  addWidget,
  addWidgetToNewSectionAt,
  allWidgetIds,
  duplicateWidget,
  emptyLayout,
  locate,
  moveWidget,
  moveWidgetToAdjacentColumn,
  moveWidgetToNewSection,
  moveWidgetToNewSectionAt,
  normalizeLayout,
  pruneLayout,
  removeSection,
  removeWidget,
  setColumnCount,
  setColumnWeight,
  setColumnWeights,
  setWidgetConfig,
  setWidgetHeight,
  setZoneHidden,
  toggleWidgetHidden,
  widgetCount,
} from './ops';
import { clearWorkspace, loadWorkspace, saveWorkspace, type StorageLike } from './persistence';
import { WORKSPACE_TEMPLATES } from './templates';
import type { WorkspaceLayout } from './types';

// ── Helpers ──────────────────────────────────────────────────────────────────

let seq = 0;
const wid = (widgetId: string): { id: string; widgetId: string; height: null } => ({
  id: `w${++seq}`,
  widgetId,
  height: null,
});

function makeLayout(shape: string[][][]): WorkspaceLayout {
  return {
    version: 1,
    sections: shape.map(sec => ({
      id: `s${++seq}`,
      columns: sec.map(col => ({ id: `c${++seq}`, weight: 3, widgets: col.map(wid) })),
    })),
  };
}

function memStorage(initial: Record<string, string> = {}): StorageLike & { data: Map<string, string> } {
  const data = new Map(Object.entries(initial));
  return {
    data,
    getItem: k => (data.has(k) ? data.get(k)! : null),
    setItem: (k, v) => { data.set(k, v); },
    removeItem: k => { data.delete(k); },
  };
}

const KNOWN = new Set(['kpi', 'perf', 'alloc', 'holdings', 'ledger', 'risk', 'health', 'mc', 'ai']);

/** Ops are Immer draft mutators; wrap each call in produce and return the result. */
type DraftOp<T extends unknown[]> = (d: WorkspaceLayout, ...args: T) => void;
function runOp<T extends unknown[]>(op: DraftOp<T>, l: WorkspaceLayout, ...args: T): WorkspaceLayout {
  return produce(l, draft => { op(draft, ...args); });
}

/** allWidgetIds for a layout; also accepts a section or column for convenience. */
const idsOf = (x: WorkspaceLayout | { columns: { widgets: { widgetId: string }[] }[] } | { widgets: { widgetId: string }[] }): string[] =>
  'sections' in x ? allWidgetIds(x as WorkspaceLayout)
    : 'columns' in x ? (x as { columns: { widgets: { widgetId: string }[] }[] }).columns.flatMap(idsOf)
    : (x as { widgets: { widgetId: string }[] }).widgets.map(w => w.widgetId);

// ── normalizeLayout ──────────────────────────────────────────────────────────

describe('normalizeLayout', () => {
  it('accepts a valid layout unchanged in structure', () => {
    const l = makeLayout([[['kpi'], ['perf']]]);
    const n = normalizeLayout(l, KNOWN);
    expect(n).not.toBeNull();
    expect(widgetCount(n!)).toBe(2);
    expect(n!.sections).toHaveLength(1);
    expect(n!.sections[0].columns).toHaveLength(2);
  });

  it('rejects non-object and sectionless payloads', () => {
    expect(normalizeLayout(null)).toBeNull();
    expect(normalizeLayout('garbage')).toBeNull();
    expect(normalizeLayout({})).toBeNull();
    expect(normalizeLayout({ sections: 'nope' })).toBeNull();
    expect(normalizeLayout({ sections: [{}] })).toBeNull();
  });

  it('drops unknown widget ids when a registry is given', () => {
    const l = makeLayout([[['kpi', 'bogus'], ['perf']]]);
    const n = normalizeLayout(l, KNOWN)!;
    expect(allWidgetIds(n)).toEqual(['kpi', 'perf']);
  });

  it('keeps unknown widgets when no registry is given', () => {
    const l = makeLayout([[['mystery']]]);
    expect(widgetCount(normalizeLayout(l)!)).toBe(1);
  });

  it('migrates legacy version-less {sections} payloads', () => {
    const legacy = { sections: [{ id: 's1', columns: [{ id: 'c1', widgets: [{ id: 'a', widgetId: 'kpi' }] }] }] };
    const n = normalizeLayout(legacy)!;
    expect(n.version).toBe(1);
    expect(allWidgetIds(n)).toEqual(['kpi']);
  });

  it('maps the legacy rail zone to right without a storage bump', () => {
    const raw = {
      sections: [{
        id: 's1',
        zone: 'rail',
        columns: [{ id: 'c1', weight: 3, widgets: [wid('kpi')] }],
      }],
    };
    const n = normalizeLayout(raw);
    expect(n!.sections[0].zone).toBe('right');
  });

  it('preserves left/right zones and hiddenZones through normalize', () => {
    const raw = {
      sections: [
        { id: 's1', zone: 'left', columns: [{ id: 'c1', weight: 3, widgets: [wid('kpi')] }] },
        { id: 's2', zone: 'right', columns: [{ id: 'c2', weight: 3, widgets: [wid('perf')] }] },
        { id: 's3', columns: [{ id: 'c3', weight: 3, widgets: [wid('alloc')] }] },
      ],
      hiddenZones: ['left', 'rail'],
    };
    const n = normalizeLayout(raw)!;
    expect(n.sections.map(s => s.zone)).toEqual(['left', 'right', 'main']);
    expect(n.hiddenZones).toEqual(['left', 'right']);
  });

  it('drops unknown zone names in hiddenZones', () => {
    const raw = {
      sections: [{ id: 's1', columns: [{ id: 'c1', weight: 3, widgets: [wid('kpi')] }] }],
      hiddenZones: ['main', 'bogus'],
    };
    expect(normalizeLayout(raw)!.hiddenZones).toBeUndefined();
  });

  it('clamps weights and de-duplicates ids', () => {
    const raw = {
      sections: [{
        id: 's1',
        columns: [
          { id: 'c1', weight: 99, widgets: [wid('kpi')] },
          { id: 'c1', weight: -4, widgets: [wid('perf')] },
          { id: 'c3', widgets: [wid('alloc')] },
        ],
      }],
    };
    const n = normalizeLayout(raw, KNOWN)!;
    expect(n.sections[0].columns).toHaveLength(3);
    expect(n.sections[0].columns[0].weight).toBe(12);
    expect(n.sections[0].columns[1].weight).toBe(0.3);
    expect(new Set(n.sections[0].columns.map(c => c.id)).size).toBe(3);  });
});

// ── moveWidget ───────────────────────────────────────────────────────────────

describe('moveWidget', () => {
  it('reorders within a column', () => {
    const l = makeLayout([[['kpi', 'perf', 'alloc']]]);
    const [col] = l.sections[0].columns;
    const moved = col.widgets[0].id;
    const n = runOp(moveWidget, l, moved, { sectionId: l.sections[0].id, columnId: col.id, index: 2 });
    expect(allWidgetIds(n)).toEqual(['perf', 'alloc', 'kpi']);
  });

  it('moves between columns in the same section', () => {
    const l = makeLayout([[['kpi', 'perf'], ['alloc']]]);
    const [c1, c2] = l.sections[0].columns;
    const n = runOp(moveWidget, l, c1.widgets[0].id, { sectionId: l.sections[0].id, columnId: c2.id, index: 0 });
    const [d1, d2] = n.sections[0].columns;
    expect(idsOf(d1)).toEqual(['perf']);
    expect(idsOf(d2)).toEqual(['kpi', 'alloc']);
  });

  it('moves across sections', () => {
    const l = makeLayout([[['kpi']], [['perf', 'alloc']]]);
    const n = runOp(moveWidget, l, l.sections[0].columns[0].widgets[0].id, {
      sectionId: l.sections[1].id,
      columnId: l.sections[1].columns[0].id,
      index: 1,
    });
    expect(allWidgetIds(n)).toEqual(['perf', 'kpi', 'alloc']);
    expect(n.sections).toHaveLength(1); // emptied section pruned
  });

  it('creates a new column when columnId is null', () => {
    const l = makeLayout([[['kpi', 'perf'], ['alloc']]]);
    const n = runOp(moveWidget, l, l.sections[0].columns[0].widgets[0].id, {
      sectionId: l.sections[0].id,
      columnId: null,
      index: 0,
    });
    expect(n.sections[0].columns).toHaveLength(3);
    expect(idsOf(n.sections[0].columns[2])).toEqual(['kpi']);
  });

  it('inserts a new column before/after an anchor via columnIndex', () => {
    const l = makeLayout([[['kpi'], ['perf'], ['alloc']]]);
    const [, c2] = l.sections[0].columns;
    // "before c2" → columnIndex 1: [kpi, NEW(alloc), perf]
    const before = runOp(moveWidget, l, l.sections[0].columns[2].widgets[0].id, {
      sectionId: l.sections[0].id, columnId: null, index: 0, columnIndex: 1,
    });
    expect(before.sections[0].columns).toHaveLength(4);
    expect(idsOf(before.sections[0].columns[1])).toEqual(['alloc']);
    expect(idsOf(before.sections[0].columns[2])).toEqual(['perf']);
    // "after c2" → columnIndex 2: [kpi, perf, NEW, (empty c3)]
    const after = runOp(moveWidget, l, c2.widgets[0].id, {
      sectionId: l.sections[0].id, columnId: null, index: 0, columnIndex: 2,
    });
    expect(after.sections[0].columns).toHaveLength(4);
    expect(idsOf(after.sections[0].columns[2])).toEqual(['perf']);
  });

  it('clamps out-of-range columnIndex to the column bounds', () => {
    const l = makeLayout([[['kpi']]]);
    const n = runOp(moveWidget, l, l.sections[0].columns[0].widgets[0].id, {
      sectionId: l.sections[0].id, columnId: null, index: 0, columnIndex: 99,
    });
    expect(n.sections[0].columns).toHaveLength(2);
    expect(idsOf(n.sections[0].columns[1])).toEqual(['kpi']);
  });

  it('clamps out-of-range indices', () => {
    const l = makeLayout([[['kpi'], ['perf']]]);
    const n = runOp(moveWidget, l, l.sections[0].columns[0].widgets[0].id, {
      sectionId: l.sections[0].id,
      columnId: l.sections[0].columns[1].id,
      index: 42,
    });
    expect(allWidgetIds(n)).toEqual(['perf', 'kpi']);
  });

  it('stacks multiple widgets vertically in one column', () => {
    const l = makeLayout([[['kpi'], ['perf'], ['alloc']]]);
    const [c1, c2, c3] = l.sections[0].columns;
    let n = runOp(moveWidget, l, c2.widgets[0].id, { sectionId: l.sections[0].id, columnId: c1.id, index: 1 });
    n = runOp(moveWidget, n, c3.widgets[0].id, { sectionId: n.sections[0].id, columnId: c1.id, index: 2 });
    expect(idsOf(n)).toEqual(['kpi', 'perf', 'alloc']);
    expect(n.sections[0].columns.filter(c => c.widgets.length > 0)).toHaveLength(1);
  });
});

describe('moveWidgetToNewSection', () => {
  it('spawns a new trailing section with the card', () => {
    const l = makeLayout([[['kpi', 'perf']]]);
    const n = runOp(moveWidgetToNewSection, l, l.sections[0].columns[0].widgets[0].id);
    expect(n.sections).toHaveLength(2);
    expect(idsOf(n.sections[1])).toEqual(['kpi']);
    expect(idsOf(n.sections[0])).toEqual(['perf']);
  });
});

describe('moveWidgetToNewSectionAt', () => {
  it('inserts a new section ABOVE the anchor (at the anchor\u2019s slot)', () => {
    const l = makeLayout([[['kpi']], [['perf']]]);
    const dragged = l.sections[1].columns[0].widgets[0].id;
    const n = runOp(moveWidgetToNewSectionAt, l, dragged, l.sections[1].id, 'above');
    // New section lands at the anchor's index; the emptied source section prunes.
    expect(n.sections).toHaveLength(2);
    expect(idsOf(n.sections[0])).toEqual(['kpi']);
    expect(idsOf(n.sections[1])).toEqual(['perf']);
  });

  it('inserts a new section ABOVE a populated anchor, between its neighbours', () => {
    const l = makeLayout([[['kpi', 'perf']], [['alloc']]]);
    const dragged = l.sections[0].columns[0].widgets[1].id;
    const n = runOp(moveWidgetToNewSectionAt, l, dragged, l.sections[1].id, 'above');
    expect(n.sections).toHaveLength(3);
    expect(idsOf(n.sections[0])).toEqual(['kpi']);   // source keeps remaining card
    expect(idsOf(n.sections[1])).toEqual(['perf']);  // new section directly above anchor
    expect(idsOf(n.sections[2])).toEqual(['alloc']); // anchor
  });

  it('inserts a new section BELOW the anchor', () => {
    const l = makeLayout([[['kpi']], [['perf']], [['alloc']]]);
    const dragged = l.sections[0].columns[0].widgets[0].id;
    const n = runOp(moveWidgetToNewSectionAt, l, dragged, l.sections[1].id, 'below');
    expect(n.sections).toHaveLength(3);
    expect(idsOf(n.sections[0])).toEqual(['perf']);  // anchor
    expect(idsOf(n.sections[1])).toEqual(['kpi']);   // new section right below anchor
    expect(idsOf(n.sections[2])).toEqual(['alloc']);
  });

  it('falls back to appending when the anchor is missing', () => {
    const l = makeLayout([[['kpi']]]);
    const dragged = l.sections[0].columns[0].widgets[0].id;
    const n = runOp(moveWidgetToNewSectionAt, l, dragged, 'nope', 'above');
    expect(n.sections).toHaveLength(1);
    expect(idsOf(n.sections[0])).toEqual(['kpi']);
  });

  it('handles dragging a section\u2019s only card onto its own strip (stays put, in place)', () => {
    const l = makeLayout([[['kpi']], [['perf']]]);
    const dragged = l.sections[1].columns[0].widgets[0].id;
    const n = runOp(moveWidgetToNewSectionAt, l, dragged, l.sections[1].id, 'below');
    // Anchor index resolved pre-take → re-inserted at the same slot.
    expect(n.sections).toHaveLength(2);
    expect(idsOf(n.sections[0])).toEqual(['kpi']);
    expect(idsOf(n.sections[1])).toEqual(['perf']);
  });
});

// ── add / remove / resize / columns ──────────────────────────────────────────

describe('add/remove', () => {
  it('adds to the end of the last column by default', () => {
    const l = makeLayout([[['kpi'], ['perf']]]);
    const n = runOp(addWidget, l, 'alloc');
    expect(allWidgetIds(n)).toEqual(['kpi', 'perf', 'alloc']);
  });

  it('adds into a brand-new column when columnId is null', () => {
    const l = makeLayout([[['kpi']]]);
    const n = runOp(addWidget, l, 'perf', { sectionId: l.sections[0].id, columnId: null, index: 0 });
    expect(n.sections[0].columns).toHaveLength(2);
  });

  it('respects columnIndex when adding into a new column', () => {
    const l = makeLayout([[['kpi'], ['perf']]]);
    const n = runOp(addWidget, l, 'alloc', { sectionId: l.sections[0].id, columnId: null, index: 0, columnIndex: 0 });
    expect(n.sections[0].columns).toHaveLength(3);
    expect(idsOf(n.sections[0].columns[0])).toEqual(['alloc']);
  });

  it('creates a section when the layout is empty', () => {
    const l: WorkspaceLayout = { version: 1, sections: [] };
    const n = runOp(addWidget, l, 'kpi');
    expect(widgetCount(n)).toBe(1);
  });

  it('removes a widget and prunes empty sections', () => {
    const l = makeLayout([[['kpi']], [['perf']]]);
    const n = runOp(removeWidget, l, l.sections[1].columns[0].widgets[0].id);
    expect(n.sections).toHaveLength(1);
    expect(allWidgetIds(n)).toEqual(['kpi']);
  });

  it('never removes the last column of a section', () => {
    const l = makeLayout([[['kpi']]]);
    const n = runOp(removeWidget, l, l.sections[0].columns[0].widgets[0].id);
    expect(n.sections).toHaveLength(1);
    expect(n.sections[0].columns).toHaveLength(1);
    expect(widgetCount(n)).toBe(0);
  });
});

describe('sections: delete + add-into-new-section', () => {
  it('removeSection drops the section and its widgets', () => {
    const l = makeLayout([[['kpi']], [['perf'], ['alloc']]]);
    const n = runOp(removeSection, l, l.sections[0].id);
    expect(n.sections).toHaveLength(1);
    expect(allWidgetIds(n)).toEqual(['perf', 'alloc']);
  });

  it('removeSection always keeps at least one section', () => {
    const l = makeLayout([[['kpi']]]);
    const n = runOp(removeSection, l, l.sections[0].id);
    expect(n.sections).toHaveLength(1);
    expect(widgetCount(n)).toBe(0);
  });

  it('addWidgetToNewSectionAt inserts a fresh single-column section above the anchor', () => {
    const l = makeLayout([[['kpi']], [['perf']]]);
    const n = runOp(addWidgetToNewSectionAt, l, 'alloc', l.sections[1].id, 'above');
    expect(n.sections).toHaveLength(3);
    expect(n.sections[1].columns).toHaveLength(1);
    expect(idsOf(n.sections[1].columns[0])).toEqual(['alloc']);
    expect(allWidgetIds(n)).toEqual(['kpi', 'alloc', 'perf']);
  });

  it('addWidgetToNewSectionAt inserts below and appends when the anchor is missing', () => {
    const l = makeLayout([[['kpi']]]);
    const below = runOp(addWidgetToNewSectionAt, l, 'alloc', l.sections[0].id, 'below');
    expect(allWidgetIds(below)).toEqual(['kpi', 'alloc']);
    const missing = runOp(addWidgetToNewSectionAt, l, 'perf', 'nope', 'above');
    expect(allWidgetIds(missing)).toEqual(['kpi', 'perf']);
  });
});

describe('columns & resize', () => {
  it('grows and shrinks column count without losing widgets', () => {
    const l = makeLayout([[['kpi'], ['perf'], ['alloc']]]);
    const shrunk = runOp(setColumnCount, l, l.sections[0].id, 1);
    expect(allWidgetIds(shrunk)).toEqual(['kpi', 'perf', 'alloc']);
    const regrown = runOp(setColumnCount, shrunk, shrunk.sections[0].id, 3);
    expect(regrown.sections[0].columns).toHaveLength(3);
    expect(allWidgetIds(regrown)).toEqual(['kpi', 'perf', 'alloc']);
  });

  it('clamps column count to 1..4', () => {
    const l = makeLayout([[['kpi']]]);
    expect(runOp(setColumnCount, l, l.sections[0].id, 9).sections[0].columns).toHaveLength(4);
    expect(runOp(setColumnCount, l, l.sections[0].id, 0).sections[0].columns).toHaveLength(1);
  });

  it('clamps weights to the column-weight range', () => {
    const l = makeLayout([[['kpi']]]);
    const colId = l.sections[0].columns[0].id;
    expect(runOp(setColumnWeight, l, colId, 100).sections[0].columns[0].weight).toBe(12);
    expect(runOp(setColumnWeight, l, colId, -3).sections[0].columns[0].weight).toBe(0.3);
  });

  it('sets widget height with a minimum', () => {
    const l = makeLayout([[['kpi']]]);
    const wid0 = l.sections[0].columns[0].widgets[0].id;
    expect(runOp(setWidgetHeight, l, wid0, 40).sections[0].columns[0].widgets[0].height).toBe(140);
    expect(runOp(setWidgetHeight, l, wid0, 320).sections[0].columns[0].widgets[0].height).toBe(320);
    expect(runOp(setWidgetHeight, l, wid0, null).sections[0].columns[0].widgets[0].height).toBeNull();
  });

  it('preserves an empty section when its column count changes', () => {
    const empty: WorkspaceLayout = { version: 1, sections: [{ id: 's1', columns: [{ id: 'c1', weight: 3, widgets: [] }] }] };
    const three = runOp(setColumnCount, empty, 's1', 3);
    expect(three.sections).toHaveLength(1);
    expect(three.sections[0].columns).toHaveLength(3);
  });

  it('setColumnWeights updates a boundary pair atomically, keeping the sum', () => {
    const l = makeLayout([[['kpi'], ['perf']]]);
    const [c0, c1] = l.sections[0].columns;
    const n = runOp(setColumnWeights, l, l.sections[0].id, [
      { columnId: c0.id, weight: 5 },
      { columnId: c1.id, weight: 1 },
    ]);
    expect(n.sections[0].columns[0].weight).toBe(5);
    expect(n.sections[0].columns[1].weight).toBe(1);
    expect(n.sections[0].columns[0].weight + n.sections[0].columns[1].weight).toBe(6);
  });
});

describe('setZoneHidden', () => {
  it('hides and restores a zone WITHOUT touching its sections', () => {
    const l = makeLayout([[['kpi']]]);
    l.sections[0].zone = 'left';
    const hidden = runOp(setZoneHidden, l, 'left', true);
    expect(hidden.hiddenZones).toEqual(['left']);
    expect(allWidgetIds(hidden)).toEqual(['kpi']); // section kept
    const shown = runOp(setZoneHidden, hidden, 'left', false);
    expect(shown.hiddenZones).toBeUndefined();
    expect(allWidgetIds(shown)).toEqual(['kpi']);
  });

  it('is idempotent and keeps zones distinct', () => {
    const l = makeLayout([[['kpi']]]);
    let n = runOp(setZoneHidden, l, 'left', true);
    n = runOp(setZoneHidden, n, 'left', true);
    expect(n.hiddenZones).toEqual(['left']);
    n = runOp(setZoneHidden, n, 'right', true);
    expect(n.hiddenZones).toEqual(['left', 'right']);
  });
});

describe('pruneLayout', () => {
  it('drops empty sections (keeps one), preserves empty columns as drop targets', () => {
    const l = makeLayout([[['kpi'], []], [[]]]);
    const n = runOp(pruneLayout, l);
    expect(n.sections).toHaveLength(1);
    expect(n.sections[0].columns).toHaveLength(2); // empty column kept for drops
    expect(allWidgetIds(n)).toEqual(['kpi']);
  });
});

// ── config / hidden / duplicate ──────────────────────────────────────────────

describe('config & hidden & duplicate', () => {
  it('merges config into a widget instance', () => {
    const l = makeLayout([[['kpi']]]);
    const wid0 = l.sections[0].columns[0].widgets[0].id;
    const n = runOp(setWidgetConfig, l, wid0, { symbol: 'NVDA', refresh: '1m' });
    expect(n.sections[0].columns[0].widgets[0].config).toEqual({ symbol: 'NVDA', refresh: '1m' });
    const n2 = runOp(setWidgetConfig, n, wid0, { refresh: '5m' });
    expect(n2.sections[0].columns[0].widgets[0].config).toEqual({ symbol: 'NVDA', refresh: '5m' });
  });

  it('toggles hidden flag on and off', () => {
    const l = makeLayout([[['kpi']]]);
    const wid0 = l.sections[0].columns[0].widgets[0].id;
    const hidden = runOp(toggleWidgetHidden, l, wid0);
    expect(hidden.sections[0].columns[0].widgets[0].hidden).toBe(true);
    const shown = runOp(toggleWidgetHidden, hidden, wid0);
    expect(shown.sections[0].columns[0].widgets[0].hidden).toBeUndefined();
  });

  it('duplicates a widget directly below the original, copying config', () => {
    const l = makeLayout([[['kpi']]]);
    const wid0 = l.sections[0].columns[0].widgets[0].id;
    const withCfg = runOp(setWidgetConfig, l, wid0, { symbol: 'NVDA' });
    const n = runOp(duplicateWidget, withCfg, wid0);
    const col = n.sections[0].columns[0];
    expect(col.widgets).toHaveLength(2);
    expect(col.widgets[0].id).toBe(wid0);
    expect(col.widgets[1].widgetId).toBe('kpi');
    expect(col.widgets[1].id).not.toBe(wid0);
    expect(col.widgets[1].config).toEqual({ symbol: 'NVDA' });
  });

  it('round-trips config and hidden through normalizeLayout', () => {
    const l = makeLayout([[['kpi']]]);
    const wid0 = l.sections[0].columns[0].widgets[0].id;
    const withCfg = runOp(setWidgetConfig, l, wid0, { symbol: 'NVDA' });
    const withHidden = runOp(toggleWidgetHidden, withCfg, wid0);
    const n = normalizeLayout(withHidden, KNOWN)!;
    expect(n.sections[0].columns[0].widgets[0].config).toEqual({ symbol: 'NVDA' });
    expect(n.sections[0].columns[0].widgets[0].hidden).toBe(true);
  });
});

// ── moveWidgetToAdjacentColumn ────────────────────────────────────────────────

describe('moveWidgetToAdjacentColumn', () => {
  it('moves a widget to the column on the right', () => {
    const l = makeLayout([[['kpi'], ['perf']]]);
    const wid0 = l.sections[0].columns[0].widgets[0].id;
    const n = runOp(moveWidgetToAdjacentColumn, l, wid0, 'right');
    expect(idsOf(n.sections[0].columns[0])).toEqual([]);
    expect(idsOf(n.sections[0].columns[1])).toEqual(['perf', 'kpi']);
  });

  it('moves a widget to the column on the left', () => {
    const l = makeLayout([[['kpi'], ['perf']]]);
    const wid1 = l.sections[0].columns[1].widgets[0].id;
    const n = runOp(moveWidgetToAdjacentColumn, l, wid1, 'left');
    expect(idsOf(n.sections[0].columns[0])).toEqual(['kpi', 'perf']);
    expect(idsOf(n.sections[0].columns[1])).toEqual([]);
  });

  it('creates a new column to the right when none exists', () => {
    const l = makeLayout([[['kpi']]]);
    const wid0 = l.sections[0].columns[0].widgets[0].id;
    const n = runOp(moveWidgetToAdjacentColumn, l, wid0, 'right');
    expect(n.sections[0].columns).toHaveLength(2);
    expect(idsOf(n.sections[0].columns[1])).toEqual(['kpi']);
  });

  it('creates a new column to the left when none exists', () => {
    const l = makeLayout([[['kpi']]]);
    const wid0 = l.sections[0].columns[0].widgets[0].id;
    const n = runOp(moveWidgetToAdjacentColumn, l, wid0, 'left');
    expect(n.sections[0].columns).toHaveLength(2);
    expect(idsOf(n.sections[0].columns[0])).toEqual(['kpi']);
  });
});

// ── Persistence ──────────────────────────────────────────────────────────────

describe('persistence', () => {
  it('round-trips a saved layout', () => {
    const s = memStorage();
    const l = makeLayout([[['kpi'], ['perf']]]);
    saveWorkspace('k', l, s);
    const res = loadWorkspace('k', emptyLayout(), { storage: s, knownWidgetIds: KNOWN });
    expect(res.corrupt).toBe(false);
    expect(allWidgetIds(res.layout)).toEqual(['kpi', 'perf']);
  });

  it('returns fallback with empty storage', () => {
    const s = memStorage();
    const fb = makeLayout([[['kpi']]]);
    const res = loadWorkspace('k', fb, { storage: s });
    expect(res.corrupt).toBe(false);
    expect(res.layout).toBe(fb);
  });

  it('falls back on corrupt JSON and does NOT overwrite the stored payload', () => {
    const raw = '{"sections":[{"columns":['; // truncated
    const s = memStorage({ k: raw });
    const fb = makeLayout([[['kpi']]]);
    const res = loadWorkspace('k', fb, { storage: s, knownWidgetIds: KNOWN });
    expect(res.corrupt).toBe(true);
    expect(res.layout).toBe(fb);
    expect(s.data.get('k')).toBe(raw);
  });

  it('falls back on structurally invalid data and does NOT overwrite', () => {
    const raw = JSON.stringify({ hello: 'world' });
    const s = memStorage({ k: raw });
    const fb = makeLayout([[['kpi']]]);
    const res = loadWorkspace('k', fb, { storage: s });
    expect(res.corrupt).toBe(true);
    expect(s.data.get('k')).toBe(raw);
  });

  it('drops widgets unknown to the registry on load', () => {
    const l = makeLayout([[['kpi', 'retired-widget']]]);
    const s = memStorage();
    saveWorkspace('k', l, s);
    const res = loadWorkspace('k', emptyLayout(), { storage: s, knownWidgetIds: KNOWN });
    expect(res.corrupt).toBe(false);
    expect(allWidgetIds(res.layout)).toEqual(['kpi']);
  });

  it('clearWorkspace removes the key', () => {
    const s = memStorage();
    saveWorkspace('k', makeLayout([[['kpi']]]), s);
    clearWorkspace('k', s);
    expect(s.data.has('k')).toBe(false);
  });
});

// ── Templates ────────────────────────────────────────────────────────────────

describe('templates', () => {
  const IDS = ['kpi', 'perf', 'alloc', 'holdings', 'ledger', 'risk', 'health', 'mc', 'ai'];

  it.each(WORKSPACE_TEMPLATES.map(t => [t.id, t] as const))('%s builds a valid, normalized layout', (_id, t) => {
    const built = t.build(IDS);
    expect(normalizeLayout(built, KNOWN)).not.toBeNull();
    expect(widgetCount(built)).toBeGreaterThan(0);
    // Every template places a contiguous prefix of the registry (no gaps in
    // which widgets are used), in any order.
    const used = allWidgetIds(built);
    expect([...used].sort()).toEqual(IDS.slice(0, widgetCount(built)).slice().sort());
    // Every section has 1..4 columns, every column ≥1 widget.
    for (const s of built.sections) {
      expect(s.columns.length).toBeGreaterThanOrEqual(1);
      expect(s.columns.length).toBeLessThanOrEqual(4);
      for (const c of s.columns) expect(c.widgets.length).toBeGreaterThanOrEqual(1);
    }
  });

  it('gracefully handles a shorter registry', () => {
    const t = WORKSPACE_TEMPLATES[0];
    const built = t.build(['kpi', 'perf']);
    expect(allWidgetIds(built)).toEqual(['kpi', 'perf']);
  });

  it('every placement round-trips through locate()', () => {
    const built = WORKSPACE_TEMPLATES[1].build(IDS);
    for (const s of built.sections) {
      for (const c of s.columns) {
        for (const w of c.widgets) {
          const loc = locate(built, w.id);
          expect(loc?.column.id).toBe(c.id);
        }
      }
    }
  });
});


import { describe, it, expect, beforeEach } from 'vitest';

// The chat's DUAL chart engine.
//
// A chart block in an answer can be drawn by EITHER engine: the interactive
// ECharts chart (the default) or the Python chart engine's drawn picture. The
// choice is a user preference, remembered across answers, and the export
// helpers must serve both.
//
// The suite runs in the node environment (no `window`), so the persistence
// itself is exercised through the store's own guard: without a browser the
// preference is in-memory only, and that is exactly what the store does.

import {
  getChatChartEngine,
  hydrateChatChartEngine,
  setChatChartEngine,
  subscribeChatChartEngine,
} from './chart-engine';
import {
  getChart,
  getChartArtifact,
  registerChart,
  registerChartArtifact,
  unregisterChart,
} from './chart-registry';

describe('the chat chart engine preference', () => {
  beforeEach(() => {
    setChatChartEngine('eclipse');
  });

  it('defaults to the interactive ECharts chart', () => {
    expect(getChatChartEngine()).toBe('eclipse');
  });

  it('carries the choice', () => {
    setChatChartEngine('python');
    expect(getChatChartEngine()).toBe('python');
  });

  it('notifies the open charts when the choice changes', () => {
    const seen: string[] = [];
    const unsubscribe = subscribeChatChartEngine((engine) => seen.push(engine));
    setChatChartEngine('python');
    unsubscribe();
    setChatChartEngine('eclipse');
    expect(seen).toEqual(['python']);
  });

  it('survives a hydration without a browser', () => {
    expect(() => hydrateChatChartEngine()).not.toThrow();
  });
});

describe('the chart registry serves both engines', () => {
  it('holds the live ECharts instance and the drawn artifact', () => {
    const instance = { id: 'live' } as never;
    registerChart('chart-1', instance);
    registerChartArtifact('chart-1', 'art_1');
    expect(getChart('chart-1')).toBe(instance);
    expect(getChartArtifact('chart-1')).toBe('art_1');
  });

  it('forgets both when the chart unmounts', () => {
    registerChart('chart-2', { id: 'live' } as never);
    registerChartArtifact('chart-2', 'art_2');
    unregisterChart('chart-2');
    expect(getChart('chart-2')).toBeNull();
    expect(getChartArtifact('chart-2')).toBeNull();
  });

  it('has no artifact for a chart the interactive engine drew', () => {
    registerChart('chart-3', { id: 'live' } as never);
    expect(getChartArtifact('chart-3')).toBeNull();
  });
});

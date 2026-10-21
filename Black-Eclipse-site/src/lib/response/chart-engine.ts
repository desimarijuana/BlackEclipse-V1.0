// ── Which engine draws a chat chart ─────────────────────────────────────────
// A chat chart block can be drawn by EITHER engine:
//
//   * `eclipse` — the interactive ECharts chart (the default, unchanged): a
//     live canvas with a crosshair, a tooltip and a legend.
//   * `python`  — the picture the Python chart engine (matplotlib) draws in
//     the runtime, fetched back as an artifact (a flat picture, no pointer
//     interaction).
//
// The choice is a USER preference, remembered across answers: someone who
// prefers the drawn picture sets it once and every chart follows.

export type ChatChartEngine = 'eclipse' | 'python';

const STORAGE_KEY = 'be_chat_chart_engine';

const listeners = new Set<(engine: ChatChartEngine) => void>();

function read(): ChatChartEngine {
  if (typeof window === 'undefined') return 'eclipse';
  try {
    return window.localStorage.getItem(STORAGE_KEY) === 'python' ? 'python' : 'eclipse';
  } catch {
    return 'eclipse';
  }
}

let current: ChatChartEngine = 'eclipse';

/** The engine chat charts are drawn with right now. */
export function getChatChartEngine(): ChatChartEngine {
  if (typeof window === 'undefined') return current;
  return current;
}

/** Choose the engine, and remember it. */
export function setChatChartEngine(engine: ChatChartEngine): void {
  current = engine;
  try {
    window.localStorage.setItem(STORAGE_KEY, engine);
  } catch {
    // A blocked storage is not a reason to fail the choice.
  }
  listeners.forEach((listener) => listener(engine));
}

/** Subscribe to engine changes (so every open chart follows the choice). */
export function subscribeChatChartEngine(listener: (engine: ChatChartEngine) => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Adopt the stored preference once the browser is available. */
export function hydrateChatChartEngine(): void {
  if (typeof window === 'undefined') return;
  const stored = read();
  if (stored !== current) {
    current = stored;
    listeners.forEach((listener) => listener(stored));
  }
}

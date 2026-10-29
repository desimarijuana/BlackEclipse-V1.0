// ── Strategy Studio workspace ───────────────────────────────────────────────
// The studio keeps everything in React state, so a reload used to lose the
// thesis, the spec, the strategy and the last result. This module is the ONE
// definition of what survives a reload and how a deep link overrides it.
//
// It is pure and storage-agnostic: the screen passes a `StorageLike`, tests pass
// an in-memory map, and nothing here touches `window` at import time.

export const STUDIO_STORAGE_KEY = "eclipse.strategy-studio.workspace.v1";
export const WORKSPACE_SCHEMA = 1;

export interface StudioWorkspace {
  schema: number;
  /** The thesis text the user is working from. */
  prompt: string;
  /** The raw editor text (the strategy spec the user is authoring). */
  editor: string;
  /** The saved strategy the workspace is bound to, when there is one. */
  strategyId: string | null;
  strategyName: string | null;
  symbol: string;
  timeframe: string;
  start: string;
  end: string;
  capital: number;
  /** The last experiment this workspace opened or produced. */
  experimentId: string | null;
  updatedAt: string;
}

export interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

export function isoDaysAgo(days: number): string {
  return new Date(Date.now() - days * 86_400_000).toISOString().slice(0, 10);
}

export function defaultWorkspace(): StudioWorkspace {
  return {
    schema: WORKSPACE_SCHEMA,
    prompt: "",
    editor: "",
    strategyId: null,
    strategyName: null,
    symbol: "BTC-USD",
    timeframe: "1d",
    start: isoDaysAgo(730),
    end: isoDaysAgo(0),
    capital: 100_000,
    experimentId: null,
    updatedAt: new Date().toISOString(),
  };
}

/** `null` when there is no usable browser storage (SSR, privacy mode). */
export function browserStorage(): StorageLike | null {
  if (typeof window === "undefined") return null;
  try {
    const probe = "__eclipse_probe__";
    window.localStorage.setItem(probe, "1");
    window.localStorage.removeItem(probe);
    return window.localStorage;
  } catch {
    return null;
  }
}

function asText(value: unknown, fallback: string): string {
  return typeof value === "string" ? value : fallback;
}

function asId(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function asCapital(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) && value > 0 ? value : fallback;
}

/**
 * Validate a stored blob. A stale or corrupt blob must never crash the screen:
 * anything unrecognised is discarded and the caller falls back to a default.
 */
export function parseWorkspace(raw: unknown): StudioWorkspace | null {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const record = raw as Record<string, unknown>;
  if (record.schema !== WORKSPACE_SCHEMA) return null;
  const fallback = defaultWorkspace();
  return {
    schema: WORKSPACE_SCHEMA,
    prompt: asText(record.prompt, ""),
    editor: asText(record.editor, ""),
    strategyId: asId(record.strategyId),
    strategyName: asId(record.strategyName),
    symbol: asText(record.symbol, fallback.symbol),
    timeframe: asText(record.timeframe, fallback.timeframe),
    start: asText(record.start, fallback.start),
    end: asText(record.end, fallback.end),
    capital: asCapital(record.capital, fallback.capital),
    experimentId: asId(record.experimentId),
    updatedAt: asText(record.updatedAt, fallback.updatedAt),
  };
}

export function loadWorkspace(storage: StorageLike | null): StudioWorkspace | null {
  if (!storage) return null;
  try {
    const text = storage.getItem(STUDIO_STORAGE_KEY);
    if (!text) return null;
    return parseWorkspace(JSON.parse(text));
  } catch {
    return null;
  }
}

export function saveWorkspace(workspace: StudioWorkspace, storage: StorageLike | null): boolean {
  if (!storage) return false;
  try {
    storage.setItem(
      STUDIO_STORAGE_KEY,
      JSON.stringify({ ...workspace, schema: WORKSPACE_SCHEMA, updatedAt: new Date().toISOString() }),
    );
    return true;
  } catch {
    return false;
  }
}

export function clearWorkspace(storage: StorageLike | null): void {
  if (!storage) return;
  try {
    storage.removeItem(STUDIO_STORAGE_KEY);
  } catch {
    // ignore: a failed clear is not worth breaking the screen over
  }
}

/**
 * Apply `?strategy=` / `?experiment=` from a deep link. Only identifiers are
 * read: the workspace itself stays the source of truth for text and inputs, so
 * a shared link reopens the saved strategy rather than stale local text.
 */
export function applyDeepLink(
  workspace: StudioWorkspace,
  search: string,
): StudioWorkspace & { wantsStrategy: boolean; wantsExperiment: boolean } {
  const raw = search.startsWith("?") ? search.slice(1) : search;
  if (!raw) return { ...workspace, wantsStrategy: false, wantsExperiment: false };
  let params: URLSearchParams;
  try {
    params = new URLSearchParams(raw);
  } catch {
    return { ...workspace, wantsStrategy: false, wantsExperiment: false };
  }
  const strategy = asId(params.get("strategy"));
  const experiment = asId(params.get("experiment"));
  return {
    ...workspace,
    strategyId: strategy ?? workspace.strategyId,
    experimentId: experiment ?? workspace.experimentId,
    wantsStrategy: Boolean(strategy),
    wantsExperiment: Boolean(experiment),
  };
}

/** The query string this workspace should leave in the address bar. */
export function workspaceQuery(workspace: Pick<StudioWorkspace, "strategyId" | "experimentId">): string {
  const params = new URLSearchParams();
  params.set("tab", "strategy-studio");
  if (workspace.strategyId) params.set("strategy", workspace.strategyId);
  if (workspace.experimentId) params.set("experiment", workspace.experimentId);
  return params.toString();
}

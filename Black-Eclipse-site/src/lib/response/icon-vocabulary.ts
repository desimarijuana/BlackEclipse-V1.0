// ── Semantic icon vocabulary (pure data + canonicalization) ──────────────────
//
// SERVER-SAFE by design: no React, no component library. The bridge capability
// that exposes this vocabulary to the agent runtime (`response_contract` →
// `schema`) imports THIS module; importing `./icons` there would pull the
// client icon set into the server route bundle and crash it (`react.createContext
// is not a function` under Next's react-server condition) — that regression is
// exactly why the mapping lives in the separate `./icons` module.
//
// `./icons` (client) maps the canonical keys below to Phosphor components.

/** The allowlisted semantic icon vocabulary. Keys are lower-kebab-case. */
export const RESPONSE_ICON_KEYS = [
  'trend-up',
  'trend-down',
  'chart',
  'allocation',
  'activity',
  'target',
  'gauge',
  'risk',
  'wallet',
  'coins',
  'dollar',
  'percent',
  'research',
  'brain',
  'database',
  'globe',
  'calendar',
  'clock',
  'history',
  'document',
  'check',
  'warning',
  'info',
  'sparkles',
  'zap',
  'search',
  'layers',
  'network',
  'workflow',
  'brain-circuit',
  'combined-chart',
  'radio',
  'cpu',
  'server',
  'gears',
  'briefcase',
  'market',
  'agent',
  'version-control',
  'list',
  'rocket',
  'pin',
] as const;

export type ResponseIconKey = (typeof RESPONSE_ICON_KEYS)[number];

const ICON_KEYS = new Set<string>(RESPONSE_ICON_KEYS);

/** True when `key` is an allowlisted semantic icon key. */
export function isResponseIconKey(key: string | undefined): key is ResponseIconKey {
  return typeof key === 'string' && ICON_KEYS.has(key);
}

/**
 * Common producer spellings that are NOT the canonical key but plainly mean it:
 * synonyms a model reaches for (`graph`, `money`, `alert`), and the emoji a model
 * often emits where a key belongs (`📈`, `⚠️`). Normalized (lower-kebab) lookups.
 * Bounded on purpose — a wrong guess here is an icon, never block loss.
 */
const ICON_TEXT_ALIASES: Record<string, ResponseIconKey> = {
  up: 'trend-up', rise: 'trend-up', rising: 'trend-up', gain: 'trend-up', gainer: 'trend-up',
  down: 'trend-down', fall: 'trend-down', falling: 'trend-down', loss: 'trend-down', loser: 'trend-down',
  graph: 'chart', 'bar-chart': 'chart', 'line-chart': 'chart', 'column-chart': 'chart',
  'pie-chart': 'allocation', pie: 'allocation', donut: 'allocation', composition: 'allocation',
  money: 'dollar', price: 'dollar', cash: 'dollar', currency: 'dollar', usd: 'dollar',
  coin: 'coins', crypto: 'coins', token: 'coins',
  percentage: 'percent', rate: 'percent', yield: 'percent',
  science: 'research', lab: 'research', experiment: 'research', flask: 'research',
  ai: 'brain', model: 'brain', reasoning: 'brain', insight: 'brain',
  db: 'database', storage: 'database', data: 'database', dataset: 'database',
  world: 'globe', global: 'globe', international: 'globe', earth: 'globe',
  date: 'calendar', schedule: 'calendar',
  time: 'clock', timer: 'clock', duration: 'clock',
  past: 'history', historical: 'history',
  file: 'document', doc: 'document', page: 'document', report: 'document', filing: 'document',
  success: 'check', ok: 'check', done: 'check', complete: 'check', checkmark: 'check', verified: 'check',
  alert: 'warning', caution: 'warning', 'warning-triangle': 'warning', important: 'warning',
  information: 'info', note: 'info', about: 'info',
  idea: 'sparkles', magic: 'sparkles', sparkle: 'sparkles', new: 'sparkles',
  bolt: 'zap', lightning: 'zap', speed: 'zap', fast: 'zap', energy: 'zap',
  magnifier: 'search', magnifying: 'search', find: 'search', lookup: 'search', magnifyingglass: 'search',
  stack: 'layers', stackoverflow: 'layers',
  nodes: 'network', connections: 'network',
  flow: 'workflow', pipeline: 'workflow', process: 'workflow', stages: 'workflow',
  goal: 'target', objective: 'target', aim: 'target',
  meter: 'gauge', progress: 'gauge', score: 'gauge',
  balance: 'wallet', account: 'wallet', cashflow: 'wallet',
  bot: 'agent', robot: 'agent', assistant: 'agent',
  git: 'version-control', branch: 'version-control', commit: 'version-control', code: 'version-control',
  checklist: 'list', todo: 'list', tasks: 'list', items: 'list', table: 'list',
  launch: 'rocket', ship: 'rocket', deploy: 'rocket', start: 'rocket',
  bookmark: 'pin', pinned: 'pin', marker: 'pin',
  bank: 'market', exchange: 'market', institution: 'market', building: 'market',
  portfolio: 'briefcase', business: 'briefcase', work: 'briefcase',
  gear: 'gears', cog: 'gears', cogs: 'gears', settings: 'gears', config: 'gears',
  host: 'server', rack: 'server', backend: 'server',
  chip: 'cpu', processor: 'cpu', hardware: 'cpu',
  broadcast: 'radio', signal: 'radio', feed: 'radio', live: 'radio',
  combo: 'combined-chart', 'combo-chart': 'combined-chart', 'combination-chart': 'combined-chart',
  neuron: 'brain-circuit', neural: 'brain-circuit', ml: 'brain-circuit',
};

const ICON_EMOJI_ALIASES: Record<string, ResponseIconKey> = {
  '📈': 'trend-up', '↗️': 'trend-up', '⬆️': 'trend-up', '🔼': 'trend-up',
  '📉': 'trend-down', '↘️': 'trend-down', '⬇️': 'trend-down', '🔽': 'trend-down',
  '📊': 'chart', '📋': 'list', '✅': 'check', '☑️': 'check',
  '⚠️': 'warning', '⚠': 'warning', '❗': 'warning',
  'ℹ️': 'info', 'ℹ': 'info',
  '🧠': 'brain', '🤖': 'agent', '🔍': 'search', '🔎': 'search',
  '🌐': 'globe', '🌍': 'globe', '🌎': 'globe',
  '💰': 'dollar', '💵': 'dollar', '💲': 'dollar', '🪙': 'coins',
  '💼': 'briefcase', '🚀': 'rocket', '⚡': 'zap', '🎯': 'target',
  '⏰': 'clock', '⏱️': 'clock', '⏱': 'clock', '⏳': 'clock', '🕐': 'clock',
  '📅': 'calendar', '📆': 'calendar',
  '🗄️': 'database', '🗄': 'database',
  '📄': 'document', '📃': 'document',
  '⚙️': 'gears', '⚙': 'gears',
  '🛡️': 'risk', '🛡': 'risk',
  '✨': 'sparkles', '📡': 'radio', '🔢': 'percent', '📌': 'pin',
};

/** `TrendUp` / `trend_up` / `trend up` / `ph-chart` → `trend-up`. */
function normalizeIconSpelling(value: string): string {
  return value
    .replace(/^(icon|ph|lucide)[:\-_\s]+/i, '')
    .replace(/([a-z0-9])([A-Z])/g, '$1-$2')
    .trim()
    .toLowerCase()
    .replace(/[\s_]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '');
}

/**
 * Canonicalize a producer-supplied icon value:
 *   * exact, re-cased or re-separated spellings resolve to the canonical key
 *     (`TrendUp`, `trend_up`, `TREND UP` → `trend-up`);
 *   * common synonyms and emoji (`graph`, `money`, `📈`) resolve to their key;
 *   * a string that is still unknown is returned UNCHANGED — the renderer
 *     degrades it to the neutral default, and the block still renders;
 *   * a non-string value (number, object, array, …) yields `undefined` so the
 *     normalizer can drop the field instead of failing the whole block.
 */
export function canonicalIconKey(raw: unknown): string | undefined {
  if (typeof raw !== 'string') return undefined;
  const trimmed = raw.trim();
  if (!trimmed) return undefined;
  if (ICON_KEYS.has(trimmed)) return trimmed;
  const emoji = ICON_EMOJI_ALIASES[trimmed];
  if (emoji) return emoji;
  const normalized = normalizeIconSpelling(trimmed);
  if (ICON_KEYS.has(normalized)) return normalized;
  return ICON_TEXT_ALIASES[normalized] ?? raw;
}

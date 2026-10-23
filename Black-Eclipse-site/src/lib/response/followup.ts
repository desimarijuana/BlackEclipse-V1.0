// ── Follow-up prompt composition (the state → model bridge) ───────────────────
// Interactive blocks handle local state in the browser. When an interaction needs
// the model, the state is serialized into plain text and fed back through the
// EXISTING agent loop (`onFollowup`) — exactly as capable as the user typing it.
//
// This is the one shared implementation of that serialization. Blocks supply
// their state, optional labels and an optional template; the helper produces the
// prompt. Keeping it here means a new interactive block gets the same safe
// interpolation (no template injection) instead of hand-rolling one.

export type FollowupValue =
  | string
  | number
  | boolean
  | null
  | undefined
  | { from: string; to: string };

export type FollowupState = Record<string, FollowupValue>;

/** A display string for one value; dates render as `from..to`. */
export function formatFollowupValue(value: FollowupValue): string {
  if (value == null) return '';
  if (typeof value === 'object') return `${value.from || '?'}..${value.to || '?'}`;
  if (typeof value === 'boolean') return value ? 'on' : 'off';
  return String(value);
}

/** Fill `{{id}}` / `{{id.from}}` / `{{id.to}}` from state. Unknown keys → ''. */
export function renderFollowupTemplate(template: string, state: FollowupState): string {
  return template.replace(/\{\{\s*([\w.]+)\s*\}\}/g, (_match, key: string) => {
    const [id, field] = key.split('.');
    const value = state[id];
    if (field && typeof value === 'object' && value !== null && (field === 'from' || field === 'to')) {
      return value[field] || '';
    }
    return formatFollowupValue(value);
  });
}

export interface ComposeFollowupOptions {
  state: FollowupState;
  /** Stable id order for the default `Label: value` form. */
  order?: readonly string[];
  /** Human labels by id; a missing label falls back to the id. */
  labels?: Record<string, string>;
  /** A stored prompt template; when present it wins over the default form. */
  template?: string;
  /** Lead phrase for the default form (e.g. the block description). */
  lead?: string;
  separator?: string;
  fallbackLead?: string;
}

/**
 * Compose a follow-up prompt from local interaction state.
 *
 * With a `template`, only `{{…}}` placeholders are interpolated — the rest of the
 * text is the producer's. Without one, the state becomes
 * `"<lead> — Label: value; Label: value"`.
 */
export function composeFollowupPrompt(options: ComposeFollowupOptions): string {
  const {
    state,
    order,
    labels,
    template,
    lead,
    separator = '; ',
    fallbackLead = 'Continue with these parameters',
  } = options;
  if (template) return renderFollowupTemplate(template, state);
  const keys = order ?? Object.keys(state);
  const parts = keys.map((id) => `${labels?.[id] ?? id}: ${formatFollowupValue(state[id])}`);
  return `${lead ?? fallbackLead} — ${parts.join(separator)}`;
}

/** Build `{ id: label }` from a list of `{ id, label }` entries. */
export function labelsById<T extends { id: string; label: string }>(items: readonly T[]): Record<string, string> {
  return Object.fromEntries(items.map((item) => [item.id, item.label]));
}

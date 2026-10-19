import type { WidgetDefinition, WidgetSurface } from './widget-def';

export interface WidgetRegistryOptions {
  surface?: WidgetSurface;
}

export interface RegisterWidgetOptions {
  replace?: boolean;
}

type Listener = () => void;

const widgets = new Map<string, WidgetDefinition>();
const listeners = new Set<Listener>();

function notify() {
  for (const listener of listeners) listener();
}

function surfaceOf(def: WidgetDefinition): WidgetSurface {
  return def.surface ?? 'both';
}

export function registerWidget(def: WidgetDefinition, opts: RegisterWidgetOptions = {}): void {
  if (widgets.has(def.id) && !opts.replace) return;
  widgets.set(def.id, def);
  notify();
}

export function unregisterWidget(id: string): boolean {
  const removed = widgets.delete(id);
  if (removed) notify();
  return removed;
}

export function getWidget(id: string): WidgetDefinition | undefined {
  return widgets.get(id);
}

export function listWidgets(opts: WidgetRegistryOptions = {}): WidgetDefinition[] {
  const values = [...widgets.values()];
  if (!opts.surface) return values;
  return values.filter((def) => {
    const surface = surfaceOf(def);
    return surface === 'both' || surface === opts.surface;
  });
}

export function subscribeWidgets(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function clearWidgetRegistry(preserve?: (id: string) => boolean): void {
  for (const id of [...widgets.keys()]) {
    if (!preserve?.(id)) widgets.delete(id);
  }
  notify();
}

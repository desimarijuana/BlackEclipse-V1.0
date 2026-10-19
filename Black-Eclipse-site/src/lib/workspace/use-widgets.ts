'use client';

import { useEffect, useState } from 'react';
import type { WidgetSurface } from './widget-def';
import { listWidgets, subscribeWidgets } from './widget-registry';

export function useWidgets(opts: { surface?: WidgetSurface } = {}) {
  const surface = opts.surface;
  const [widgets, setWidgets] = useState(() => listWidgets({ surface }));

  useEffect(() => {
    const update = () => setWidgets(listWidgets({ surface }));
    const unsubscribe = subscribeWidgets(update);
    update();
    return unsubscribe;
  }, [surface]);

  return widgets;
}

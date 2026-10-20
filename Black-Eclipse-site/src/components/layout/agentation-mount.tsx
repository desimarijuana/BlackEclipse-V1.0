'use client';

// Dev-only review toolbar. The toolbar bundle is ~1 MB, so it is imported in an
// effect AND only when the build-time flag is on — never on a normal page load.
// (A static/dynamic import in the server layout still emitted the chunk in the
// initial script list even when the flag was off.)

import { useEffect, useState, type ComponentType } from 'react';

export function AgentationMount() {
  const [Toolbar, setToolbar] = useState<ComponentType | null>(null);

  useEffect(() => {
    if (process.env.NEXT_PUBLIC_AGENTATION !== '1') return;
    let live = true;
    void import('@/components/layout/agentation-toolbar')
      .then((m) => {
        if (live) setToolbar(() => m.AgentationToolbar);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);

  return Toolbar ? <Toolbar /> : null;
}

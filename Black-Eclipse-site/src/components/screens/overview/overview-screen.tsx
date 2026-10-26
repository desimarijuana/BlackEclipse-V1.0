'use client';

// ── Agentic Overview ─────────────────────────────────────────────────────────
// The Agentic-mode landing page: the workflow gallery (view/open/create) without
// the Graph Studio editor chrome. Opening or creating a workflow routes to the
// Graph Studio tab, where the editor takes over.

import { GraphHome } from '../graph-studio/graph-home';

export function OverviewScreen({ onOpenWorkflow }: { onOpenWorkflow: () => void }) {
  return (
    <GraphHome
      eyebrow="Agentic workspace"
      title="Overview"
      subtitle="Your workflows at a glance. Open one to keep editing, or start a new one."
      showExit={false}
      onOpen={onOpenWorkflow}
    />
  );
}

'use client';

// ── Graph Overview ──────────────────────────────────────────────────────────
// The ONE Graph-mode page. It hosts the full Graph Studio workspace: the
// workflow gallery (view/open/create) and, once a workflow is opened, the
// editor. There is no separate "Graph Studio" tab — Overview is the entry point
// and the editor lives in-place behind the gallery's back button.

import { GraphStudioScreen } from '../graph-studio/graph-studio-screen';

export function OverviewScreen({ onEditorChange }: { onEditorChange?: (editing: boolean) => void }) {
  return (
    <GraphStudioScreen
      eyebrow=""
      title="Overview"
      subtitle="Your workflows at a glance. Open one to keep editing, or start a new one."
      onViewChange={onEditorChange}
    />
  );
}

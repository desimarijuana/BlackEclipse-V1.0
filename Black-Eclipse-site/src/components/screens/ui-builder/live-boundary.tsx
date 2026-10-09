'use client';

// ── Live-render error boundary ────────────────────────────────────────────────
// The UI Builder can render a widget through the SAME host implementation the
// published dashboard uses. A widget that throws (missing data source, bad
// config) must not take down the builder, so each live-rendered instance is
// wrapped here and degrades to a readable fallback.

import React from 'react';

interface Props { label: string; children: React.ReactNode }
interface State { error: string | null }

export class LiveBoundary extends React.Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: unknown): State {
    return { error: error instanceof Error ? error.message : 'render failed' };
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex h-full items-center justify-center p-2 text-center text-[10px] text-amber-300/80">
          {this.props.label}: {this.state.error}
        </div>
      );
    }
    return this.props.children;
  }
}

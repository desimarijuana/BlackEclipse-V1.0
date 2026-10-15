'use client';

import React from 'react';
import { AlertTriangle, RefreshCw, RotateCcw } from '@/lib/icons';

interface Props {
  children: React.ReactNode;
}

interface State {
  hasError: boolean;
  message: string;
}

/**
 * Catches render errors in the subtree and shows a graceful fallback
 * instead of crashing the whole app.
 */
export class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, message: '' };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, message: error.message || 'Something went wrong' };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[ErrorBoundary]', error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-[100dvh] w-full items-center justify-center p-6">
          <div className="relative w-full max-w-md overflow-hidden rounded-2xl border border-rose-500/25 glass-card">
            {/* Rose wash sits OVER the glass so the surface still frosts (a solid
                fill would flatten the blur). */}
            <span
              aria-hidden
              className="pointer-events-none absolute inset-0 bg-gradient-to-br from-rose-500/[0.12] via-rose-500/[0.04] to-transparent"
            />
            <div className="relative flex flex-col items-center gap-3 px-6 py-8 text-center">
              <span className="flex h-12 w-12 items-center justify-center rounded-2xl border border-rose-500/30 bg-rose-500/15 text-rose-300">
                <AlertTriangle size={22} />
              </span>
              <div>
                <h2 className="text-base font-semibold tracking-tight text-foreground">Something went wrong</h2>
                <p className="mt-1 max-w-sm break-words text-[13px] leading-relaxed text-muted-foreground">
                  {this.state.message}
                </p>
              </div>
              <div className="mt-1 flex flex-wrap items-center justify-center gap-2">
                <button
                  onClick={() => this.setState({ hasError: false, message: '' })}
                  className="inline-flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 cursor-pointer"
                >
                  <RotateCcw size={14} /> Try again
                </button>
                <button
                  onClick={() => window.location.reload()}
                  className="inline-flex items-center gap-1.5 rounded-full px-3.5 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-white/5 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/20 cursor-pointer"
                >
                  <RefreshCw size={13} /> Reload
                </button>
              </div>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

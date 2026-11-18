import { StockChat } from '@/components/screens/stock-chat';
import { ErrorBoundary } from '@/components/ui/error-boundary';
import { UiCatalogSync } from '@/components/layout/ui-catalog-sync';
import { ChunkReloadGuard } from '@/components/layout/chunk-reload-guard';
import { GraphScreenPrefetch } from '@/components/layout/graph-prefetch';
import { onboardingGateState } from '@/lib/setup/gate';

// The page must be rendered per request: it reads the first-run flag.
export const dynamic = 'force-dynamic';

/**
 * Stands in for the app shell while the first-run wizard owns the screen.
 *
 * Mounting the shell (`StockChat`) behind the wizard opened long-lived SSE
 * streams and ~30 boot requests. Browsers allow six concurrent HTTP/1.1
 * connections per origin, so the wizard's `POST /api/setup` could sit in that
 * queue and never be sent — the "stuck on Saving…" a new install hit. The
 * wizard is a full-screen overlay (z-200) rendered by the root layout, so
 * nothing here is visible.
 */
function SetupPlaceholder() {
  return (
    <div className="fixed inset-0 flex items-center justify-center bg-background">
      <p className="text-[12px] text-muted-foreground">Starting Eclipse…</p>
    </div>
  );
}

export default async function Page() {
  if ((await onboardingGateState()) === 'incomplete') return <SetupPlaceholder />;

  return (
    <ErrorBoundary>
      <ChunkReloadGuard />
      <GraphScreenPrefetch />
      <UiCatalogSync />
      <StockChat />
    </ErrorBoundary>
  );
}

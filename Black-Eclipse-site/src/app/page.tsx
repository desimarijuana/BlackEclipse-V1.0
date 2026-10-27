import { StockChat } from '@/components/screens/stock-chat';
import { ErrorBoundary } from '@/components/ui/error-boundary';
import { UiCatalogSync } from '@/components/layout/ui-catalog-sync';
import { ChunkReloadGuard } from '@/components/layout/chunk-reload-guard';

export default function Page() {
  return (
    <ErrorBoundary>
      <ChunkReloadGuard />
      <UiCatalogSync />
      <StockChat />
    </ErrorBoundary>
  );
}
